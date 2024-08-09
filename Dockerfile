# Use an official Python runtime as the base image
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update
RUN apt-get install -y openssh-client

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt
RUN ssh-keygen -q -t rsa -N '' -f colterm


EXPOSE 2022
EXPOSE 22

# Run the Python script when the container launches
CMD ["python", "term.py"]
