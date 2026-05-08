# Use a combined image that has both Python and Java 17 pre-installed
FROM ghcr.io/graalvm/jdk-community:17

# Install Python 3 and pip
RUN microdnf install -y python3 python3-pip && microdnf clean all

# Set the working directory
WORKDIR /app

# Copy the dependencies list and install them
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy all backend files into the container
COPY . .

# Force the symbolic link so it doesn't crash if 'python' already exists
RUN ln -sf /usr/bin/python3 /usr/bin/python

# Start the FastAPI server using the entry point in main.py
# We use python3 explicitly to be safe
CMD ["python3", "main.py"]
