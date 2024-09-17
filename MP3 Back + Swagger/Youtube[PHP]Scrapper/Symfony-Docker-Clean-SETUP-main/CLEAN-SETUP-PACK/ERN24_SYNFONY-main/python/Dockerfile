# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt ./

# Install the dependencies specified in the requirements file
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY app.py .
COPY swagger.yaml .

# Expose the port the app runs on
EXPOSE 5000

# Command to run the Flask application
CMD ["python", "app.py"]

# ... other instructions ...

RUN mkdir -p /var/www/html/public/converted_files && \
    chown -R www-data:www-data /var/www/html && \
    chmod -R 775 /var/www/html/public/converted_files

USER www-data