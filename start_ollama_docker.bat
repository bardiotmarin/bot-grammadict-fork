@echo off
echo Starting Ollama Container with RTX 2080 Ti GPU...
docker compose up -d

echo.
echo Pulling llama3.2-vision model (11B Vision - Optimized for RTX 2080 Ti VRAM)...
docker exec -it ollama_gpu ollama pull llama3.2-vision

echo.
echo Ollama is ready on http://localhost:11434 !
pause
