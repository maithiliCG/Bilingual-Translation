"""Custom exception classes."""


class PipelineError(Exception):
    """Base exception for pipeline errors."""
    pass


class PDFProcessingError(PipelineError):
    """Error during PDF processing."""
    pass


class GLMOCRError(PipelineError):
    """Error from GLM-OCR API."""
    pass


class TranslationError(PipelineError):
    """Error during translation."""
    pass


class ReconstructionError(PipelineError):
    """Error during layout reconstruction."""
    pass
