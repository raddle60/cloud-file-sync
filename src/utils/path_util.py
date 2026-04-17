"""
Path utility functions for cross-platform path handling.
"""
import os


class PathUtil:
    """
    Utility class wrapping os.path.join with standardized behavior.
    Only supports two parameters: dir and path.
    Automatically handles paths starting with / or \ (strips them from path).
    """

    @staticmethod
    def join(dir: str, path: str) -> str:
        """
        Join two path components, handling paths starting with / or \\.

        Args:
            dir: The directory path
            path: The relative path (can start with / or \\)

        Returns:
            Joined path with normalized separators
        """
        # Strip leading / or \ from path to avoid absolute path issues
        clean_path = path.lstrip(r'\/')
        return os.path.join(dir, clean_path)
