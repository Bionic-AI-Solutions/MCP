"""
Nano Banana Gemini Client Wrapper

Provides async-friendly wrapper around Google Gemini API for image generation and editing.
Supports concurrency control via semaphores.
"""

import asyncio
import base64
from typing import Dict, List, Any, Optional
from io import BytesIO

try:
    from google import genai
    try:
        from google.genai import types
    except ImportError:
        # Fallback for different versions
        try:
            from google.generativeai import types
        except ImportError:
            types = None
except ImportError:
    genai = None
    types = None


class NanoBananaClientWrapper:
    """Wrapper around Gemini client for async operations with concurrency control."""

    def __init__(self, client: Any, semaphore: asyncio.Semaphore, model: str = "gemini-2.0-flash-exp"):
        self.client = client
        self.semaphore = semaphore
        self.model = model

    async def generate_image(
        self,
        prompt: str,
        output_path: Optional[str] = None,
        width: int = 1024,
        height: int = 1024,
    ) -> Dict[str, Any]:
        """Generate an image using Gemini's image generation capabilities.
        
        Args:
            prompt: Text description of the image to generate
            output_path: Optional path to save the image
            width: Image width in pixels
            height: Image height in pixels
        """
        async with self.semaphore:
            try:
                # Use Gemini's image generation API
                # Note: This is a simplified implementation - adjust based on actual Gemini API
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="image/png",
                    ),
                )
                
                # Extract image data from response
                # The actual structure depends on Gemini API response format
                image_data = None
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data'):
                                image_data = part.inline_data.data
                            elif hasattr(part, 'data'):
                                image_data = part.data
                
                if not image_data:
                    # Fallback: try to get image from response directly
                    if hasattr(response, 'data'):
                        image_data = response.data
                
                if image_data:
                    # Decode base64 if needed
                    if isinstance(image_data, str):
                        image_bytes = base64.b64decode(image_data)
                    else:
                        image_bytes = image_data
                    
                    # Save to file if path provided
                    if output_path:
                        with open(output_path, 'wb') as f:
                            f.write(image_bytes)
                    
                    return {
                        "success": True,
                        "image_data": base64.b64encode(image_bytes).decode('utf-8'),
                        "output_path": output_path,
                        "width": width,
                        "height": height,
                        "format": "png",
                    }
                else:
                    return {
                        "success": False,
                        "error": "No image data in response",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def edit_image(
        self,
        image_path: str,
        prompt: str,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Edit an existing image using Gemini.
        
        Args:
            image_path: Path to the input image
            prompt: Description of the edit to make
            output_path: Optional path to save the edited image
        """
        async with self.semaphore:
            try:
                # Read image file
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()
                
                # Convert to base64
                image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                
                # Use Gemini to edit the image
                # This is a simplified implementation - adjust based on actual Gemini API
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=[
                        {
                            "role": "user",
                            "parts": [
                                {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                                {"text": prompt},
                            ],
                        }
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="image/png",
                    ),
                )
                
                # Extract edited image data
                image_data = None
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data'):
                                image_data = part.inline_data.data
                            elif hasattr(part, 'data'):
                                image_data = part.data
                
                if image_data:
                    if isinstance(image_data, str):
                        edited_bytes = base64.b64decode(image_data)
                    else:
                        edited_bytes = image_data
                    
                    if output_path:
                        with open(output_path, 'wb') as f:
                            f.write(edited_bytes)
                    
                    return {
                        "success": True,
                        "image_data": base64.b64encode(edited_bytes).decode('utf-8'),
                        "output_path": output_path,
                    }
                else:
                    return {
                        "success": False,
                        "error": "No edited image data in response",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def generate_content(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate text content using Gemini.
        
        Args:
            prompt: Text prompt for content generation
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
        """
        async with self.semaphore:
            try:
                config = types.GenerateContentConfig(temperature=temperature)
                if max_tokens:
                    config.max_output_tokens = max_tokens
                
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                
                text = ""
                if hasattr(response, 'text'):
                    text = response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content'):
                        if hasattr(candidate.content, 'parts'):
                            text = " ".join(
                                part.text for part in candidate.content.parts
                                if hasattr(part, 'text')
                            )
                        elif hasattr(candidate.content, 'text'):
                            text = candidate.content.text
                
                return {
                    "success": True,
                    "text": text,
                    "model": self.model,
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }
