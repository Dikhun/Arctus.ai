#cloud-config
package_update: true
package_upgrade: true

packages:
  - python3-pip
  - python3-venv
  - git
  - curl
  - docker.io

runcmd:
  # Enable Docker
  - systemctl start docker
  - systemctl enable docker
  - usermod -aG docker ubuntu

  # Create an isolated workspace for the agent framework
  - mkdir -p /opt/agent-workspace
  - chown ubuntu:ubuntu /opt/agent-workspace

  # Setup a Python virtual environment and install standard orchestration libraries
  - su - ubuntu -c "python3 -m venv /opt/agent-workspace/venv"
  - su - ubuntu -c "/opt/agent-workspace/venv/bin/pip install openai requests"

write_files:
  - path: /opt/agent-workspace/.env
    permissions: '0600'
    owner: ubuntu:ubuntu
    content: |
      # Add your provider keys here
      OPENAI_API_KEY=sk-your-key-here

