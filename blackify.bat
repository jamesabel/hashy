call venv\Scripts\activate.bat
python -m black -l 192 hashy test_hashy setup.py
deactivate
