# FastAPI CRUD CI/CD on EC2 (Jenkins + Ansible + Docker)

End‑to‑end CI/CD for a containerized FastAPI CRUD app: Jenkins builds → pushes Docker image to DockerHub → Ansible deploys to EC2.

---

## Architecture (High‑Level)

1. **Developer** pushes code to GitHub (`main` branch).
2. **Jenkins (EC2/Ubuntu 22.04)** pulls repo → builds Docker image → pushes to **DockerHub**.
3. **Ansible (from Jenkins host)** connects to target EC2 host(s) and runs the updated container.
4. **App** is exposed on port **8000** (HTTP) on the target instance.

> **Security Groups:** open **22** (SSH), **8080** (Jenkins UI), **8000** (App) as needed.

---

## Repository Structure

```
fastapi-crud/
├─ app/
│  └─ main.py
├─ ansible.cfg               # Ansible config (host_key_checking, inventory path)
├─ deploy.yml                # Ansible playbook: pull & run container
├─ Dockerfile
├─ hosts                     # Ansible inventory
├─ Jenkinsfile
├─ requirements.txt
└─ README.md                 # (this file)
```

---

## 1) Launch Jenkins EC2 (Ubuntu 22.04)

* **Instance type:** `t2.medium` (recommended for Jenkins + Docker)
* **Open ports:** `22` (SSH), `8080` (Jenkins), `8000` (App)

---

## 2) Install Dependencies on Jenkins EC2

Run the following on the Ubuntu 22.04 instance (as a sudoer).

### 2.1 Check OS

```bash
cat /etc/os-release
```

### 2.2 Install Java (JDK)

```bash
sudo apt update -y
sudo apt install -y default-jdk
java --version
```

### 2.3 Install Docker Engine

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
"$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update -y
apt-cache policy docker-ce
sudo apt install -y docker-ce
sudo systemctl enable --now docker
sudo systemctl status docker --no-pager
```

### 2.4 Install Python 3 + pip

```bash
sudo apt install -y python3 python3-pip
python3 --version
```

### 2.5 Install Ansible

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository --yes --update ppa:ansible/ansible
sudo apt update -y
sudo apt install -y ansible
ansible --version
```

### 2.6 Install Jenkins

```bash
sudo wget -O /usr/share/keyrings/jenkins-keyring.asc https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key
sudo sh -c 'echo deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian binary/ > /etc/apt/sources.list.d/jenkins.list'

sudo apt update -y
sudo apt install -y jenkins
sudo systemctl enable --now jenkins
sudo systemctl status jenkins --no-pager
```

### 2.7 Post‑Install (Docker group for Jenkins & your user)

```bash
# Allow jenkins and ubuntu users to run docker without sudo
sudo usermod -aG docker jenkins
sudo usermod -aG docker $USER
# start a new shell with updated groups (or log out/in)
newgrp docker

# If Jenkins already running, restart so group change takes effect
sudo systemctl restart jenkins
```

### 2.8 Unlock Jenkins & Plugins

* Open: `http://<EC2_PUBLIC_IP>:8080` (e.g., `http://13.218.90.91:8080`)
* Get initial admin password:

  ```bash
  sudo cat /var/lib/jenkins/secrets/initialAdminPassword
  ```
* Install **Suggested plugins**, plus ensure: **Git**, **Pipeline**, **Pipeline: Stage View**, **Docker**, **Ansible**.
* Create an admin user.

---

## 3) Create the FastAPI CRUD App (locally)

```bash
mkdir fastapi-crud && cd fastapi-crud
```

**app/main.py**

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()
items = {}

@app.get("/")
def read_root():
    return {"msg": "FastAPI CRUD running!"}

@app.post("/items/{item_id}")
def create_item(item_id: int, name: str):
    if item_id in items:
        raise HTTPException(status_code=400, detail="Item exists")
    items[item_id] = name
    return {"item_id": item_id, "name": name}

@app.get("/items/{item_id}")
def read_item(item_id: int):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Not found")
    return {"item_id": item_id, "name": items[item_id]}

@app.put("/items/{item_id}")
def update_item(item_id: int, name: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Not found")
    items[item_id] = name
    return {"item_id": item_id, "name": name}

@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Not found")
    del items[item_id]
    return {"msg": "Deleted"}
```

**requirements.txt**

```text
fastapi
uvicorn[standard]
```

---

## 4) Dockerize the App

**Dockerfile**

```dockerfile
FROM python:3.9
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Test locally**

```bash
docker build -t fastapi-crud .
docker run -d -p 8000:8000 --name fastapi-crud fastapi-crud
# Open http://localhost:8000
```

---

## 5) Push Code to GitHub

```bash
git init
git remote add origin https://github.com/<your-username>/fastapi-crud.git
git add .
git commit -m "FastAPI CRUD initial"
git branch -M main
git push -u origin main
```

---

## 6) Prepare DockerHub

* Create a **DockerHub** repo: `fastapi-crud`
* Login **on Jenkins EC2** (for manual test):

```bash
docker login -u <your-dockerhub-username> -p <your-password>
```

* In **Jenkins → Manage Credentials**, add a **Secret Text** or **Username/Password** credential ID like `dockerhub-pass`.

> The pipeline uses `${DOCKERHUB_USER}` and `${DOCKERHUB_PASS}` (credential ID: `dockerhub-pass`).

---

## 7) Ansible Deployment Files (in repo root)

**deploy.yml**

```yaml
- hosts: all
  become: true
  tasks:
    - name: Stop old container (ignore if missing)
      shell: docker rm -f fastapi-crud || true

    - name: Pull latest image
      shell: docker pull <dockerhub-username>/fastapi-crud:latest

    - name: Run new container
      shell: docker run -d --name fastapi-crud -p 8000:8000 <dockerhub-username>/fastapi-crud:latest
```

**hosts** (Inventory)

```ini
# Use the correct SSH username for your target EC2 AMI.
# Ubuntu AMI → ubuntu ;  Amazon Linux → ec2-user
13.218.90.9 ansible_ssh_user=ec2-user ansible_ssh_private_key_file=/home/ec2-user/.ssh/id_rsa ansible_ssh_common_args='-o StrictHostKeyChecking=no'

[local]
localhost ansible_connection=local
```

**ansible.cfg**

```ini
[defaults]
inventory = ./hosts
host_key_checking = False
retry_files_enabled = False
forks = 10
```

> **Note:** Ensure the **target EC2** (inventory host) has **Docker installed** and port **8000** open in its security group.

---

## 8) Jenkins Pipeline (Declarative)

**Jenkinsfile**

```groovy
pipeline {
  agent any

  environment {
    DOCKERHUB_USER = '<your-dockerhub-username>'
    DOCKERHUB_PASS = credentials('dockerhub-pass') // Jenkins secret credential
  }

  stages {
    stage('Checkout') {
      steps {
        git branch: 'main', url: 'https://github.com/<your-username>/fastapi-crud.git'
      }
    }

    stage('Build Docker Image') {
      steps {
        sh 'docker build -t ${DOCKERHUB_USER}/fastapi-crud:latest .'
      }
    }

    stage('Push to DockerHub') {
      steps {
        sh "echo ${DOCKERHUB_PASS} | docker login -u ${DOCKERHUB_USER} --password-stdin"
        sh "docker push ${DOCKERHUB_USER}/fastapi-crud:latest"
      }
    }

    stage('Deploy with Ansible') {
      steps {
        sh 'ansible-playbook -i hosts deploy.yml'
      }
    }
  }
}
```

---

## 9) Create the Jenkins Job

1. **Dashboard → New Item →** *Pipeline*
2. **Name:** `fastapi-cicd`
3. **Pipeline** → *Pipeline script from SCM*
4. **SCM:** Git
5. **Repo URL:** `https://github.com/<your-username>/fastapi-crud.git`
6. **Branch:** `main`
7. **Script Path:** `Jenkinsfile`
8. **Save**

(Optional) Enable **Build Triggers → Poll SCM** with `H/5 * * * *`.

---

## 10) Run the Pipeline

* Push a new commit to `main` or click **Build Now** in Jenkins.
* Stages: **Checkout → Build → Push → Deploy**.

---

## 11) Verify Deployment

Open the app:

```
http://<EC2_APP_IP>:8000/
```

Expected response:

```json
{"msg": "FastAPI CRUD running!"}
```

---

## Troubleshooting & Tips

* **`docker: permission denied` in Jenkins:** ensure `jenkins` is in `docker` group and restart Jenkins.
* **Ansible SSH issues:** verify inventory username (`ubuntu` vs `ec2-user`), key path, and security group port 22.
* **Image not updating:** confirm the tag is `latest` in both push and `docker run`, and that the deploy host pulls before running.
* **Port 8000 unreachable:** check target EC2 security group and any OS firewall (UFW) rules.
* **Docker on target host:** install Docker on the **deployment target** (Ansible can manage this or install manually) before running the playbook.

---

## Clean Up

```bash
# Stop/remove container on target host
sudo docker rm -f fastapi-crud || true
# (Optional) remove local images
docker rmi <your-dockerhub-username>/fastapi-crud:latest || true
```

