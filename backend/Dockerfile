# Use a lightweight Python 3.9 base image
FROM python:3.9-slim

# Install OpenJDK 17
# Your JvmTraceAgent requires the Java Debug Interface (JDI), 
# which is included in the JDK.
RUN apt-get update && \
    apt-get install -y openjdk-17-jdk-headless && \
    apt-get clean;

# Set the internal working directory for the container
WORKDIR /app

# Copy the dependencies list and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend files into the container
COPY . .

# Launch the server using the entry point in your main.py
CMD ["python", "main.py"]