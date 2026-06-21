@echo off
echo ================================
echo BRAND ENGINE SETUP
echo ================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
if not exist .env (
    copy .env.example .env
    echo Created .env file.
)
if not exist data\products mkdir data\products
if not exist data\reports mkdir data\reports
if not exist data\sessions mkdir data\sessions
if not exist data\autopsies mkdir data\autopsies
if not exist data\queue.txt echo. > data\queue.txt
echo.
echo ================================
echo SETUP COMPLETE
echo ================================
echo.
echo NEXT STEPS:
echo 1. Open .env and add your:
echo    - ANTHROPIC_API_KEY
echo    - DISCORD_WEBHOOK_URL
echo.
echo 2. Run run.bat to start
echo.
echo Need help? See README.md
echo ================================
pause
