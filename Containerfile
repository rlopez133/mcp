FROM registry.access.redhat.com/ubi9/python-311:latest

RUN pip install mcp["cli"]

WORKDIR /mcp_server

COPY . /mcp_server

EXPOSE 8000

ENTRYPOINT [ "python", "ansible.py" ]
