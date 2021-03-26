pushd .
cd ..
del /Q hashy.egg-info\*.*
del /Q build\*.*
del /Q dist\*.*
copy /Y LICENSE LICENSE.txt
call venv\Scripts\activate.bat
python.exe setup.py bdist_wheel
twine upload dist/*
call deactivate
popd
