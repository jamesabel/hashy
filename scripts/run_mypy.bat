pushd .
cd ..
call venv\Scripts\activate.bat 
mypy -m hashy
mypy -m test_hashy
call deactivate
popd
