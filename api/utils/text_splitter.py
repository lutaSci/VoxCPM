"""
Smart text splitting for TTS generation.
Splits long text into manageable segments while preserving semantic meaning.
"""
import re
from typing import List


class TextSplitter:
    """
    Smart text splitter that breaks text into segments for TTS generation.
    
    Strategy:
    1. First try to split by major punctuation (。！？；\n) - semantic boundaries
    2. If segment still too long, split by secondary punctuation (，、：)
    3. If still too long, split by spaces or character limit
    """
    
    # Primary delimiters - strong semantic boundaries
    PRIMARY_DELIMITERS = r'[。！？；\n]'
    # Secondary delimiters - weaker boundaries
    SECONDARY_DELIMITERS = r'[，、：:,;]'
    # Quote patterns to handle
    QUOTE_PATTERNS = r'["""\'\'「」『』【】]'
    
    def __init__(self, max_length: int = 300):
        """
        Initialize the text splitter.
        
        Args:
            max_length: Maximum characters per segment
        """
        self.max_length = max_length
    
    def split(self, text: str) -> List[str]:
        """
        Split text into segments.
        
        Args:
            text: Input text to split
            
        Returns:
            List of text segments
        """
        if not text or not text.strip():
            return []
        
        # Normalize whitespace
        text = self._normalize_text(text)
        
        # If text is short enough, return as-is
        if len(text) <= self.max_length:
            return [text]
        
        # First pass: split by primary delimiters
        segments = self._split_by_pattern(text, self.PRIMARY_DELIMITERS)
        
        # Second pass: further split segments that are still too long
        result = []
        for segment in segments:
            if len(segment) <= self.max_length:
                result.append(segment)
            else:
                # Try secondary delimiters
                sub_segments = self._split_by_pattern(segment, self.SECONDARY_DELIMITERS)
                for sub in sub_segments:
                    if len(sub) <= self.max_length:
                        result.append(sub)
                    else:
                        # Hard split by max_length at word boundaries
                        result.extend(self._hard_split(sub))
        
        # Filter empty segments and strip
        result = [s.strip() for s in result if s.strip()]
        
        # Merge very short segments with neighbors if possible
        result = self._merge_short_segments(result, min_length=20)
        
        return result
    
    def _normalize_text(self, text: str) -> str:
        """Normalize whitespace and clean up text."""
        # Replace multiple newlines with single
        text = re.sub(r'\n+', '\n', text)
        # Replace multiple spaces with single
        text = re.sub(r' +', ' ', text)
        # Strip
        text = text.strip()
        return text
    
    def _split_by_pattern(self, text: str, pattern: str) -> List[str]:
        """
        Split text by regex pattern while keeping delimiters attached.
        
        Args:
            text: Text to split
            pattern: Regex pattern for delimiters
            
        Returns:
            List of segments with delimiters attached to preceding text
        """
        # Split but keep delimiter
        parts = re.split(f'({pattern})', text)
        
        # Recombine: attach delimiter to preceding text
        segments = []
        current = ""
        
        for i, part in enumerate(parts):
            if re.match(pattern, part):
                # This is a delimiter, attach to current
                current += part
                if current.strip():
                    segments.append(current)
                current = ""
            else:
                current += part
        
        # Don't forget the last part
        if current.strip():
            segments.append(current)
        
        return segments
    
    def _hard_split(self, text: str) -> List[str]:
        """
        Hard split text when no good delimiter found.
        Tries to split at word boundaries (spaces) when possible.
        
        Args:
            text: Text to split
            
        Returns:
            List of segments
        """
        segments = []
        remaining = text
        
        while len(remaining) > self.max_length:
            # Try to find a space near the max_length boundary
            split_point = self.max_length
            
            # Look backwards for a space (prefer word boundary)
            search_start = max(0, self.max_length - 50)
            space_pos = remaining.rfind(' ', search_start, self.max_length)
            
            if space_pos > search_start:
                split_point = space_pos
            
            # Also check for Chinese/Japanese word boundaries (harder)
            # For now, just use the found position or max_length
            
            segment = remaining[:split_point].strip()
            if segment:
                segments.append(segment)
            remaining = remaining[split_point:].strip()
        
        if remaining:
            segments.append(remaining)
        
        return segments
    
    def _merge_short_segments(self, segments: List[str], min_length: int = 20) -> List[str]:
        """
        Merge very short segments with their neighbors.
        
        Args:
            segments: List of segments
            min_length: Minimum desired segment length
            
        Returns:
            Merged segments
        """
        if len(segments) <= 1:
            return segments
        
        result = []
        i = 0
        
        while i < len(segments):
            current = segments[i]
            
            # If current is short and we can merge with next
            while (len(current) < min_length and 
                   i + 1 < len(segments) and 
                   len(current) + len(segments[i + 1]) <= self.max_length):
                i += 1
                current = current + segments[i]
            
            result.append(current)
            i += 1
        
        return result


# Singleton instance with default settings
default_splitter = TextSplitter(max_length=300)


def smart_split(text: str, max_length: int = 300) -> List[str]:
    """
    Convenience function for smart text splitting.
    
    Args:
        text: Input text
        max_length: Maximum characters per segment
        
    Returns:
        List of text segments
    """
    if max_length == 300:
        return default_splitter.split(text)
    return TextSplitter(max_length=max_length).split(text)
