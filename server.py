import json
import os # <--- ДОБАВИТЬ ЭТО
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google import genai
from google.genai import types

app = FastAPI()

# Берем ключ из безопасного хранилища переменных окружения
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Allow the frontend to talk to this server (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. The Rulebook
system_instruction = """
You are an expert mechanical engineer and SolidWorks Python API developer.
Write a Python script using win32com.client to automate SolidWorks based on the user's parameters and image.
CRITICAL RULE: Output ONLY valid Python code. Do NOT wrap the code in markdown blocks (do not use ```python).
"""

# 3. The API Endpoint
@app.post("/generate")
async def generate_script(data: str = Form(...), image: UploadFile = File(None)):
    
    # Unpack the JSON sent by the frontend
    params = json.loads(data)
    
    # Build a highly detailed prompt using the frontend data
    user_prompt = f"""
    Create a SolidWorks Python script using these exact parameters:
    - Problem Description: {params['prompt']}
    - Material: {params['material']['name']} (E={params['material']['youngsModulusGPa']} GPa, Poisson={params['material']['poissonsRatio']}, Yield={params['material']['yieldStrengthMPa']} MPa)
    - Geometry: Length={params['geometry']['lengthM']}m, Width={params['geometry']['widthM']}m, Height={params['geometry']['heightM']}m
    - Fixture: {params['loads']['fixture']}
    - Force: {params['loads']['forceN']} N
    - Mesh Density: {params['mesh']}
    """

    contents = [user_prompt]

    # If the user uploaded an image, attach it!
    if image:
        image_bytes = await image.read()
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=image.content_type)
        contents.append(image_part)

    # Ask Gemini to generate the code
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_instruction)
        )
        
        # Clean up the response just in case the AI added markdown backticks
        clean_code = response.text.replace("```python", "").replace("```", "").strip()
        
        # Send the raw code back to the frontend
        # Clean up the response just in case the AI added markdown backticks
        clean_code = response.text.replace("```python", "").replace("```", "").strip()
        
        # Собираем JSON по требуемой структуре
        response_data = {
            "code": clean_code,
            "parsed": {
                "lengthM": params['geometry']['lengthM'],
                "widthM": params['geometry']['widthM'],
                "heightM": params['geometry']['heightM'],
                "fixture": params['loads']['fixture'],
                "forceN": params['loads']['forceN'],
                "materialName": params['material']['name'],
                "yieldStrengthMPa": params['material']['yieldStrengthMPa']
            }
        }
        
        return JSONResponse(content=response_data)

    except Exception as e:
        print(f"\n🚨 CRASH REPORT: {str(e)}\n")
        
        # --- CHANGE THIS LINE ---
        # Build a JSON response even for errors so the frontend doesn't break
        error_data = {
            "code": f"# ERROR generating code: {str(e)}",
            "parsed": {} 
        }
        return JSONResponse(content=error_data, status_code=500)

if __name__ == "__main__":
    import uvicorn
    # Starts the server on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
    