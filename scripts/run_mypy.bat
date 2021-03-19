pushd .
cd ..
call venv\Scripts\activate.bat 
mypy -m hashy
call deactivate
popd
