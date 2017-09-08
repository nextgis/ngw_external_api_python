class NGWResourceModelJobError(Exception):
    """Common error"""
    def __init__(self, msg):
        super(NGWResourceModelJobError, self).__init__()
        self.msg = msg

    def __str__(self):
        return self.msg

class JobError(NGWResourceModelJobError):
	"""Specific job error"""
	def __init__(self, msg, wrapped_exception=None):
		super(JobError, self).__init__(msg)
		self.wrapped_exception = wrapped_exception

class JobWarning(NGWResourceModelJobError):
	"""Specific job warning"""
	def __init__(self, msg ):
		super(JobWarning, self).__init__(msg)

class JobInternalError(NGWResourceModelJobError):
	"""Unexpected job error. With trace"""
	def __init__(self, msg, trace):
		super(JobInternalError, self).__init__(msg)
		self.trace = trace

class JobServerRequestError(NGWResourceModelJobError):
	"""Something wrong with request to NGW like  no connection, 502, ngw error """
	def __init__(self, msg, url):
		super(JobServerRequestError, self).__init__(msg)
		self.url = url

class JobNGWError(JobServerRequestError):
	"""NGW answer is received, but NGW cann't execute request for perform the job"""
	def __init__(self, msg, url):
		super(JobNGWError, self).__init__(msg, url)


class JobAuthorizationError(JobNGWError):
	"""NGW cann't execute request for perform the job because user does not have rights"""
	def __init__(self, url):
		super(JobAuthorizationError, self).__init__("", url)
