@echo off
REM Proxy Calil/Vegas no PC. Defina TOKEN antes (mesmo do EasyPanel SCRAPE_PROXY_TOKEN).
if "%TOKEN%"=="" (
  echo Defina TOKEN, ex.: set TOKEN=seu-segredo
  exit /b 1
)
cd /d "%~dp0"
set HOST=127.0.0.1
set PORT=8788
node server.mjs
