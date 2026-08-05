@echo off
title llama.cpp server
cd /d "C:\Users\terry\llama-cpp-turboquant\build\bin\Release"
.\llama-server.exe --model "C:\Users\terry\llama-cpp-turboquant\models\gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf" -fa on --cont-batching --no-kv-unified -ctk turbo3 -ctv turbo3 -to 1800 -fit on --swa-full --ctx-checkpoints 1 -np 3 --host 127.0.0.1 --port 8080 -c 56384 --temperature 0.55 --repeat-penalty 1.12 --top-p 0.9 --top-k 40 --jinja
echo.
echo [llama.cpp ended - check messages above for errors]
pause
