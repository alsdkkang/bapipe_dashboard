docker build -t bapipe-keypoints-testbuild-telfer -f ./docker/Dockerfile.testbuild .
docker run -it --rm -v `pwd`:/project bapipe-keypoints-testbuild-telfer 

