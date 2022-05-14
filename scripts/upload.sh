rm -rf dist
python3 -m build
python3 -m twine upload --verbose dist/*
python3 -m pip install --verbose --no-deps bapipe-keypoints-telfer
