DOCKER_IMAGE=andretelfer/bapipe-keypoints-build-telfer:1.0.0
docker pull $DOCKER_IMAGE
docker run -it --rm -p 8888:8888 -v $HOME:/home/jovyan/shared $DOCKER_IMAGE start-notebook.sh

