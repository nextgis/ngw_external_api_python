import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Union,
)

from osgeo import gdal, osr
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFileUtils,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterFileWriter,
    QgsRasterLayer,
    QgsRasterPipe,
)

from nextgis_connect.compat import DataType
from nextgis_connect.exceptions import DataPreparationError
from nextgis_connect.logging import logger
from nextgis_connect.ngw_api.qgis.qgis_ngw_connection import QgsNgwConnection

UPLOADABLE_SUFFIXES = frozenset((".tif", ".tiff", ".jpg", ".jpeg", ".png"))
UPLOADABLE_DRIVER_SUFFIXES = {
    "GTiff": ".tif",
    "JPEG": ".jpg",
    "PNG": ".png",
}
GEOTIFF_SUFFIX = ".tif"
CRS_SIDECAR_SUFFIX = ".prj"
NGW_CONNECTION_ID_PROPERTY = "ngw_connection_id"
NGW_RESOURCE_ID_PROPERTY = "ngw_resource_id"
TEMPORARY_FILE_PREFIX = "nextgis-connect-"


@dataclass(frozen=True)
class PreparedRasterFile:
    """Represent a prepared raster upload payload."""

    upload_path: Path
    is_temporary: bool
    is_archive: bool


class RasterUploadPreparer:
    """Prepare raster layers for server upload."""

    def __init__(
        self,
        work_dir: Optional[Path] = None,
    ) -> None:
        """Create a raster upload preparer."""
        self._work_dir = work_dir

    def prepare(self, layer: QgsRasterLayer) -> PreparedRasterFile:
        """Prepare a raster layer for upload."""
        if not layer.isValid():
            raise DataPreparationError("Raster layer is not valid")

        source_crs = layer.crs()
        if not source_crs.isValid():
            raise DataPreparationError("Raster layer CRS is not valid")

        source_path = self._source_file_path(layer)
        main_path: Optional[Path] = None
        main_is_temporary = False

        if self._is_uploadable_source(source_path):
            logger.debug(
                "Raster layer %s can be uploaded from original path",
                layer.name(),
            )
            main_path = source_path
            main_is_temporary = False

        elif self._is_ngw_layer(layer):
            main_path = self._download_ngw_layer(layer)
            if main_path is not None:
                main_is_temporary = True
            else:
                logger.warning(
                    "Raster layer %s has NGW source metadata but cannot be "
                    "downloaded, will be exported to GeoTIFF",
                    layer.name(),
                )

        if main_path is None:
            logger.debug(
                "Raster layer %s will be exported to GeoTIFF",
                layer.name(),
            )
            main_path = self._convert_to_geotiff(layer)
            main_is_temporary = True

        sidecar_paths = tuple(self._collect_sidecar_files(main_path))
        need_crs_sidecar = (
            source_crs.isValid() and source_crs.postgisSrid() == 0
        )
        need_archive = bool(sidecar_paths) or need_crs_sidecar

        if not need_archive:
            return PreparedRasterFile(
                upload_path=main_path,
                is_temporary=main_is_temporary,
                is_archive=False,
            )

        sidecar_names = ", ".join(str(path.name) for path in sidecar_paths)

        logger.debug(
            "Raster layer %s will be uploaded as an archive with sidecars: %s",
            layer.name(),
            sidecar_names,
        )

        archive_path = self._build_archive(
            main_path=main_path,
            sidecar_paths=sidecar_paths,
            crs=source_crs if need_crs_sidecar else None,
        )

        if main_is_temporary:
            self._remove_dataset(main_path, sidecar_paths)

        return PreparedRasterFile(
            upload_path=archive_path,
            is_temporary=True,
            is_archive=True,
        )

    def _is_uploadable_source(self, source_path: Optional[Path]) -> bool:
        """Check if a raster layer can be uploaded from its original source."""
        return bool(
            source_path
            and source_path.exists()
            and source_path.suffix.lower() in UPLOADABLE_SUFFIXES
        )

    def _is_ngw_layer(self, layer: QgsRasterLayer) -> bool:
        """Check if a raster layer has NGW source metadata for possible download."""
        return (
            layer.customProperty(NGW_CONNECTION_ID_PROPERTY) is not None
            and layer.customProperty(NGW_RESOURCE_ID_PROPERTY) is not None
        )

    def _convert_to_geotiff(self, layer: QgsRasterLayer) -> Path:
        """Export a raster layer to GeoTIFF using QGIS providers."""
        provider = layer.dataProvider()
        output_path = self._temporary_path(GEOTIFF_SUFFIX)

        pipe = QgsRasterPipe()
        if not pipe.set(provider.clone()):
            raise DataPreparationError(
                f"Cannot clone raster data provider for layer {layer.name()}"
            )

        raster_writer = QgsRasterFileWriter(str(output_path))
        raster_writer.setOutputFormat("GTiff")
        raster_writer.setOutputProviderKey("gdal")
        raster_writer.setBuildPyramidsFlag(Qgis.RasterBuildPyramidOption.No)

        logger.debug(
            "Starting GeoTIFF export for raster layer %s to %s. "
            "This may take a while for large or remote rasters.",
            layer.name(),
            output_path,
        )

        transform_context = QgsProject.instance().transformContext()
        result = raster_writer.writeRaster(
            pipe,
            provider.xSize(),
            provider.ySize(),
            layer.extent(),
            layer.crs(),
            transform_context,
        )

        if result != Qgis.RasterFileWriterResult.Success:
            raise DataPreparationError(
                f"Cannot write raster layer {layer.name()} to GeoTIFF: {result}"
            )

        self._fix_converted_data_type_if_needed(layer, output_path)
        self._restore_exported_crs_if_needed(layer, output_path)

        return output_path

    def _fix_converted_data_type_if_needed(
        self,
        layer: QgsRasterLayer,
        raster_path: Path,
    ) -> None:
        """Restore source raster data type after QGIS export if needed."""
        provider = layer.dataProvider()
        if provider is None:
            raise DataPreparationError(
                f"Raster layer {layer.name()} has no data provider"
            )

        band_number = 1
        source_type = provider.dataType(band_number)
        if source_type == Qgis.DataType.UnknownDataType:
            raise DataPreparationError(
                f"Cannot determine data type for band {band_number} of "
                f"provider {provider.name()}"
            )

        source_gdal_type = DataType(source_type).to_gdal()

        dataset = gdal.Open(str(raster_path))
        if dataset is None:
            raise DataPreparationError(
                f"Cannot open exported raster with GDAL: {raster_path}"
            )

        band = dataset.GetRasterBand(1)
        if band is None:
            dataset = None
            raise DataPreparationError(
                f"Exported raster has no first band: {raster_path}"
            )

        if band.DataType == source_gdal_type:
            dataset = None
            logger.debug(
                "Converted raster data type matches source data type for %s",
                raster_path,
            )
            return

        logger.debug(
            "Raster data type will be fixed from %s to %s for %s",
            band.DataType,
            source_gdal_type,
            raster_path,
        )

        fixed_path = raster_path.with_name(
            f"{raster_path.stem}_fixed{raster_path.suffix}"
        )

        options = gdal.TranslateOptions(
            format="GTiff",
            outputType=source_gdal_type,
        )
        fixed_dataset = gdal.Translate(
            str(fixed_path),
            dataset,
            options=options,
        )

        dataset = None
        del fixed_dataset

        if not fixed_path.exists():
            raise DataPreparationError(
                f"Cannot create fixed raster file: {fixed_path}"
            )

        self._replace_dataset(fixed_path, raster_path)

    def _restore_exported_crs_if_needed(
        self,
        layer: QgsRasterLayer,
        raster_path: Path,
    ) -> None:
        """Write layer CRS back to an exported raster if it was lost."""
        target_crs = layer.crs()
        if not target_crs.isValid():
            raise DataPreparationError(
                f"Raster layer CRS is not valid for {layer.name()}"
            )

        dataset = gdal.Open(str(raster_path), gdal.GA_Update)
        if dataset is None:
            raise DataPreparationError(
                f"Cannot open exported raster for CRS validation: {raster_path}"
            )

        projection = dataset.GetProjection()
        if projection:
            dataset = None
            logger.debug("Converted raster CRS is present for %s", raster_path)
            return

        crs_definition = self._crs_to_string(target_crs).strip()
        spatial_reference = osr.SpatialReference()
        if (
            not crs_definition
            or spatial_reference.SetFromUserInput(crs_definition) != 0
        ):
            dataset = None
            raise DataPreparationError(
                f"Cannot serialize CRS for exported raster: {raster_path}"
            )

        logger.debug("Restoring missing CRS for %s", raster_path)
        dataset.SetSpatialRef(spatial_reference)
        dataset.FlushCache()
        dataset = None

        verified_dataset = gdal.Open(str(raster_path))
        if verified_dataset is None:
            raise DataPreparationError(
                f"Cannot reopen exported raster after CRS restore: {raster_path}"
            )

        restored_projection = verified_dataset.GetProjection()
        verified_dataset = None

        if not restored_projection:
            raise DataPreparationError(
                f"Cannot restore CRS for exported raster: {raster_path}"
            )

    def _build_archive(
        self,
        main_path: Path,
        sidecar_paths: Sequence[Path],
        crs: Optional[QgsCoordinateReferenceSystem],
    ) -> Path:
        """Build a ZIP archive with raster dataset files."""
        archive_path = self._temporary_path(".zip", keep_file=True)

        entries: Dict[str, Path] = {main_path.name: main_path}
        for sidecar_path in sidecar_paths:
            entries.setdefault(sidecar_path.name, sidecar_path)

        crs_archive_name = f"{main_path.stem}{CRS_SIDECAR_SUFFIX}"
        if crs is not None:
            entries.pop(crs_archive_name, None)

        with zipfile.ZipFile(
            str(archive_path),
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for archive_name, file_path in entries.items():
                archive.write(str(file_path), arcname=archive_name)

            if crs is not None:
                archive.writestr(crs_archive_name, self._crs_to_string(crs))

        return archive_path

    def _temporary_path(self, suffix: str, keep_file: bool = False) -> Path:
        """Create a temporary output path."""
        directory = str(self._work_dir) if self._work_dir else None
        descriptor, raw_path = tempfile.mkstemp(
            prefix=TEMPORARY_FILE_PREFIX,
            suffix=suffix,
            dir=directory,
        )
        os.close(descriptor)

        path = Path(raw_path)
        if not keep_file:
            self._unlink_if_exists(path)

        return path

    def _source_file_path(self, layer: QgsRasterLayer) -> Optional[Path]:
        """Return a local file path from a raster layer URI if possible."""
        source = layer.source()
        direct_path = Path(source)
        if direct_path.exists():
            return direct_path

        metadata = QgsProviderRegistry.instance().providerMetadata(
            layer.providerType()
        )
        if metadata is None:
            return None

        try:
            uri_parts = metadata.decodeUri(source)
        except Exception:
            return None

        path_value = uri_parts.get("path")
        if not path_value:
            return None

        decoded_path = Path(str(path_value))
        if decoded_path.exists():
            return decoded_path

        return None

    def _download_ngw_layer(self, layer: QgsRasterLayer) -> Optional[Path]:
        """Download the original NGW raster source when layer metadata allows."""
        connection_id = layer.customProperty(NGW_CONNECTION_ID_PROPERTY)
        resource_id = layer.customProperty(NGW_RESOURCE_ID_PROPERTY)

        if not connection_id or resource_id is None:
            return None

        try:
            normalized_resource_id = int(resource_id)
        except (TypeError, ValueError):
            return None

        output_path = self._temporary_path(".download")
        logger.debug(
            "Downloading original NGW raster source for layer %s "
            "from resource %s before upload preparation.",
            layer.name(),
            normalized_resource_id,
        )

        try:
            QgsNgwConnection(str(connection_id)).download(
                f"/api/resource/{normalized_resource_id}/download",
                str(output_path),
            )
        except Exception:
            self._unlink_if_exists(output_path)
            raise

        return self._normalize_downloaded_raster_path(output_path)

    def _normalize_downloaded_raster_path(self, raster_path: Path) -> Path:
        """Rename a downloaded raster to a known uploadable suffix if possible."""
        dataset = gdal.Open(str(raster_path))
        if dataset is None:
            return raster_path

        driver = dataset.GetDriver()
        dataset = None

        driver_name = None if driver is None else driver.ShortName
        if not isinstance(driver_name, str):
            return raster_path

        suffix = UPLOADABLE_DRIVER_SUFFIXES.get(driver_name)
        if suffix is None or raster_path.suffix.lower() == suffix:
            return raster_path

        normalized_path = raster_path.with_suffix(suffix)
        self._unlink_if_exists(normalized_path)
        raster_path.replace(normalized_path)

        logger.debug(
            "Normalized downloaded raster path from %s to %s based on GDAL driver %s",
            raster_path,
            normalized_path,
            driver_name,
        )
        return normalized_path

    def _raster_layer_from_path(
        self,
        raster_path: Path,
        layer_name: str,
    ) -> QgsRasterLayer:
        """Open a local raster path as a GDAL-backed raster layer."""
        layer = QgsRasterLayer(str(raster_path), layer_name, "gdal")
        if not layer.isValid():
            raise DataPreparationError(
                f"Cannot open raster source for export: {raster_path}"
            )

        return layer

    def _replace_dataset(
        self,
        source_path: Path,
        target_path: Path,
    ) -> None:
        """Replace a raster dataset and retarget generated sidecars."""
        source_sidecars = tuple(self._collect_sidecar_files(source_path))
        target_sidecars = tuple(self._collect_sidecar_files(target_path))

        for sidecar_path in target_sidecars:
            self._unlink_if_exists(sidecar_path)

        source_path.replace(target_path)

        for source_sidecar in source_sidecars:
            target_sidecar = self._retarget_sidecar_path(
                source_sidecar,
                source_path,
                target_path,
            )
            source_sidecar.replace(target_sidecar)

    def _retarget_sidecar_path(
        self,
        sidecar_path: Path,
        old_base_path: Path,
        new_base_path: Path,
    ) -> Path:
        """Return a sidecar path retargeted to another raster base path."""
        old_name_prefix = f"{old_base_path.name}."
        if sidecar_path.name.startswith(old_name_prefix):
            suffix = sidecar_path.name[len(old_base_path.name) :]
            return new_base_path.with_name(f"{new_base_path.name}{suffix}")

        old_stem_prefix = f"{old_base_path.stem}."
        if sidecar_path.name.startswith(old_stem_prefix):
            suffix = sidecar_path.name[len(old_base_path.stem) :]
            return new_base_path.with_name(f"{new_base_path.stem}{suffix}")

        return new_base_path.with_name(sidecar_path.name)

    def _collect_sidecar_files(
        self, source: Union[Path, QgsRasterLayer]
    ) -> List[Path]:
        """Return existing sidecar files for a raster dataset path."""
        sidecar_paths: Set[Path] = set()

        possible_paths = []
        if not isinstance(source, QgsRasterLayer):
            possible_paths = QgsFileUtils.sidecarFilesForPath(str(source))
        else:
            metadata = QgsProviderRegistry.instance().providerMetadata(
                source.providerType()
            )
            possible_paths = metadata.sidecarFilesForUri(source.source())

        for file_path in possible_paths:
            candidate = Path(str(file_path))
            if candidate.exists():
                sidecar_paths.add(candidate)

        return sorted(sidecar_paths)

    def _crs_to_string(self, crs: QgsCoordinateReferenceSystem) -> str:
        """Return a CRS definition suitable for sidecar storage."""
        wkt = crs.toWkt()
        if wkt:
            return f"{wkt}\n"

        proj = crs.toProj()
        if proj:
            return f"{proj}\n"

        raise DataPreparationError("Cannot serialize CRS definition")

    def _remove_dataset(
        self, path: Path, sidecar_paths: Sequence[Path]
    ) -> None:
        """Remove a temporary raster dataset and its known sidecars."""
        self._unlink_if_exists(path)

        for sidecar_path in sidecar_paths:
            self._unlink_if_exists(sidecar_path)

    def _unlink_if_exists(self, path: Path) -> None:
        """Remove a file if it exists."""
        try:
            path.unlink()
        except FileNotFoundError:
            return
