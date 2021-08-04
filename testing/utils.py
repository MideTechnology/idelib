class nullcontext:
    """ A replacement for `contextlib.nullcontext` for python versions before 3.7
    """

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
