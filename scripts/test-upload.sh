rm -rf dist
python3 -m build
python3 -m twine upload --verbose --repository testpypi dist/*
python3 -m pip install --verbose --index-url https://test.pypi.org/simple/ --no-deps bapipe-keypoints-telfer