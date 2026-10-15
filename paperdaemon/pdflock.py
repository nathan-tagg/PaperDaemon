"""PDFium (through pypdfium2) is not safe to call from two threads at once: the engine draws a document's page and
its thumbnails on several request threads, and calls running together failed with PdfiumError ("PDF RENDER
FAILED" on the page). Every use of PDFium in PaperDaemon holds this lock, from opening the document to closing it.
"""
import threading

LOCK = threading.RLock()
