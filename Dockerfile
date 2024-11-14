FROM python:3.9.6

# Install dependencies
RUN apt-get update
RUN apt-get -y install python3 python3-pip

RUN mkdir /app
# Copy your code to the container (IMPORTANT: make sure you submit everything in this directory and check that the Dockerfile works with a fresh copy of your repository)
COPY . /app
WORKDIR /app


# # Install additional requirements
RUN python3 -m pip install -r requirements.txt


# Run your project
CMD python3 run.py
