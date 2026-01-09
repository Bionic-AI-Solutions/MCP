"""
GenImage Runware Client Wrapper

Provides async-friendly wrapper around Runware API for image generation.
Supports concurrency control via semaphores.
"""

import asyncio
import base64
import uuid
from typing import Dict, Any, Optional
from io import BytesIO

import httpx


class GenImageClientWrapper:
    """Wrapper around Runware API client for async operations with concurrency control."""

    def __init__(
        self,
        api_key: str,
        semaphore: asyncio.Semaphore,
        base_url: str = "https://api.runware.ai/v1",
    ):
        self.api_key = api_key
        self.semaphore = semaphore
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(300.0),  # 5 minutes for image generation
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        model: Optional[str] = None,
        steps: int = 40,
        cfg_scale: float = 5.0,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate an image using Runware API.
        
        Based on Runware API documentation:
        https://docs.runware.ai/
        
        Args:
            prompt: Text description of the image to generate
            width: Image width in pixels (default: 1024)
            height: Image height in pixels (default: 1024)
            model: Model ID (default: civitai:943001@1055701 - SDXL-based)
            steps: Number of inference steps (default: 40)
            cfg_scale: CFG scale (default: 5.0)
            output_path: Optional path to save the image
        """
        async with self.semaphore:
            try:
                # Default model: SDXL-based
                if model is None:
#                    model = "civitai:943001@1055701"
                    model = "runware:400@1"
                
                task_uuid = str(uuid.uuid4())
                
                # Runware API requires payload to be an array
                payload = [{
                    "taskType": "imageInference",
                    "taskUUID": task_uuid,
                    "positivePrompt": prompt,
                    "width": width,
                    "height": height,
                    "model": model,
                    "steps": steps,
                    "CFGScale": cfg_scale,
                }]
                
                # Make API request
                response = await self.client.post("/image-inference", json=payload)
                response.raise_for_status()
                api_response = response.json()
                
                # Runware API returns {"data": [...]} or direct array
                if isinstance(api_response, dict) and "data" in api_response:
                    # Response has data array
                    data_array = api_response["data"]
                    if isinstance(data_array, list) and len(data_array) > 0:
                        result = data_array[0]
                    else:
                        return {
                            "success": False,
                            "error": f"No data in response: {api_response}",
                        }
                elif isinstance(api_response, list) and len(api_response) > 0:
                    # Direct array response
                    result = api_response[0]
                else:
                    return {
                        "success": False,
                        "error": f"Unexpected response format: {api_response}",
                    }
                
                # Extract image URL or base64 data
                image_url = None
                image_data = None
                
                # Check for image URL in response
                if "imageURL" in result:
                    image_url = result["imageURL"]
                elif "imageUrl" in result:
                    image_url = result["imageUrl"]
                elif "url" in result:
                    image_url = result["url"]
                
                # If we have a URL, download the image
                if image_url:
                    img_response = await self.client.get(image_url)
                    img_response.raise_for_status()
                    image_data = img_response.content
                elif "imageData" in result:
                    # Base64 encoded image
                    image_data = base64.b64decode(result["imageData"])
                elif "data" in result:
                    # Direct binary data
                    if isinstance(result["data"], str):
                        image_data = base64.b64decode(result["data"])
                    else:
                        image_data = result["data"]
                
                if image_data:
                    # Save to file if path provided
                    if output_path:
                        with open(output_path, 'wb') as f:
                            f.write(image_data)
                    
                    return {
                        "success": True,
                        "image_data": base64.b64encode(image_data).decode('utf-8'),
                        "output_path": output_path,
                        "width": width,
                        "height": height,
                        "format": "png",
                        "task_uuid": task_uuid,
                    }
                else:
                    return {
                        "success": False,
                        "error": "No image data in response",
                        "response": result,
                    }
            except httpx.HTTPStatusError as e:
                return {
                    "success": False,
                    "error": f"HTTP error: {e.response.status_code} - {e.response.text}",
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def upscale_image(
        self,
        image_data: str,  # Base64-encoded image or file path
        scale: int = 2,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upscale an image using Runware API.
        
        Args:
            image_data: Base64-encoded image data or file path
            scale: Upscale factor (default: 2)
            output_path: Optional path to save the upscaled image
        """
        async with self.semaphore:
            try:
                # Handle file path or base64
                if isinstance(image_data, str) and len(image_data) < 200:
                    # Assume it's a file path
                    with open(image_data, 'rb') as f:
                        image_bytes = f.read()
                    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                else:
                    # Assume it's base64
                    image_b64 = image_data
                
                task_uuid = str(uuid.uuid4())
                
                payload = {
                    "taskType": "imageUpscale",
                    "taskUUID": task_uuid,
                    "imageBase64": image_b64,
                    "scale": scale,
                }
                
                response = await self.client.post("/image-upscale", json=payload)
                response.raise_for_status()
                result = response.json()
                
                # Extract upscaled image
                upscaled_data = None
                if "imageURL" in result:
                    img_response = await self.client.get(result["imageURL"])
                    img_response.raise_for_status()
                    upscaled_data = img_response.content
                elif "imageData" in result:
                    upscaled_data = base64.b64decode(result["imageData"])
                
                if upscaled_data:
                    if output_path:
                        with open(output_path, 'wb') as f:
                            f.write(upscaled_data)
                    
                    return {
                        "success": True,
                        "image_data": base64.b64encode(upscaled_data).decode('utf-8'),
                        "output_path": output_path,
                        "scale": scale,
                    }
                else:
                    return {
                        "success": False,
                        "error": "No upscaled image data in response",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def remove_background(
        self,
        image_data: str,  # Base64-encoded image or file path
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Remove background from an image using Runware API.
        
        Args:
            image_data: Base64-encoded image data or file path
            output_path: Optional path to save the processed image
        """
        async with self.semaphore:
            try:
                # Handle file path or base64
                if isinstance(image_data, str) and len(image_data) < 200:
                    with open(image_data, 'rb') as f:
                        image_bytes = f.read()
                    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                else:
                    image_b64 = image_data
                
                task_uuid = str(uuid.uuid4())
                
                payload = {
                    "taskType": "imageBackgroundRemoval",
                    "taskUUID": task_uuid,
                    "imageBase64": image_b64,
                    "model": "runware:109@1",  # RemBG 1.4
                }
                
                response = await self.client.post("/image-background-removal", json=payload)
                response.raise_for_status()
                result = response.json()
                
                # Extract processed image
                processed_data = None
                if "imageURL" in result:
                    img_response = await self.client.get(result["imageURL"])
                    img_response.raise_for_status()
                    processed_data = img_response.content
                elif "imageData" in result:
                    processed_data = base64.b64decode(result["imageData"])
                
                if processed_data:
                    if output_path:
                        with open(output_path, 'wb') as f:
                            f.write(processed_data)
                    
                    return {
                        "success": True,
                        "image_data": base64.b64encode(processed_data).decode('utf-8'),
                        "output_path": output_path,
                    }
                else:
                    return {
                        "success": False,
                        "error": "No processed image data in response",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }
