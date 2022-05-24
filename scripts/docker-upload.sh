DOCKER_IMAGE=andretelfer/bapipe-keypoints-build-telfer:1.0.0
docker build -t $DOCKER_IMAGE -f ../docker/Dockerfile.run .
docker push $DOCKER_IMAGE

