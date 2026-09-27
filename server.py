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
You are an expert mechanical engineer. 
Analyze the provided image and text prompt. Extract the physical parameters (length, force, etc.) prioritizing the values visible in the IMAGE.
You MUST output ONLY a valid JSON object with EXACTLY this structure, nothing else:
{
  "code": "Python win32com script here as a plain string",
  "parsed": {
    "lengthM": float,
    "widthM": float,
    "heightM": float,
    "fixture": "string",
    "forceN": float,
    "materialName": "string",
    "yieldStrengthMPa": float
  }
}
Do not use markdown formatting (no ```json).
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
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json" # Заставляем вернуть JSON
            )
        )
        
        # Нейросеть уже вернула нам готовый JSON, мы просто пересылаем его на фронтенд
        ai_json_data = json.loads(response.text.strip())
        return JSONResponse(content=ai_json_data)
        
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
        error_msg = str(e)
        print(f"\n🚨 CRASH REPORT: {error_msg}\n")
        
        # Проверяем, это перегрузка Google (503) или другая ошибка
        if "503" in error_msg or "UNAVAILABLE" in error_msg:
            user_message = "# Сервер нейросети временно перегружен. Пожалуйста, подождите минуту и нажмите Generate снова."
            status = 503
        else:
            user_message = f"# Произошла ошибка при генерации: {error_msg}"
            status = 500
            
        error_data = {
            "code": user_message,
            "parsed": {} 
        }
        return JSONResponse(content=error_data, status_code=status)

if __name__ == "__main__":
    import uvicorn
    # Starts the server on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
    
