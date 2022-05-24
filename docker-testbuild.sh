DOCKER_IMAGE=andretelfer/bapipe-keypoints-build-telfer:1.0.0
docker build -t $DOCKER_IMAGE -f ./docker/Dockerfile.testbuild .
docker run -it --rm -v `pwd`:/project $DOCKER_IMAGE

