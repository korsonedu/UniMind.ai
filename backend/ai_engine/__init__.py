class AIExecutionCancelled(Exception):
    """The caller revoked this run while the model or tools were active."""

    def __init__(self, error):
        super().__init__(str(error))
        self.error = error
