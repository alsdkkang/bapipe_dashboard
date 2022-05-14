docker build -t bapipe-keypoints-build-telfer -f ./docker/Dockerfile.build .
docker run -it --rm -v `pwd`:/project bapipe-keypoints-build-telfer 

