docker build -t bapipe-keypoints-telfer -f ./docker/Dockerfile.run .

# Open jupyter notebook on port 8888
docker run -it --rm -p 8888:8888 -v $HOME:/home/jovyan/shared bapipe-keypoints-telfer start-notebook.sh

