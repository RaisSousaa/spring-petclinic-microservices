import os
import random
import uuid
from locust import HttpUser, task, between

class BasePetClinicUser(HttpUser):
    abstract = True
    # Intervalo de espera entre requisições de cada usuário virtual
    wait_time = between(1, 2)

    def get_owners(self):
        self.client.get("/api/customer/owners", name="/api/customer/owners")

    def get_owner_by_id(self):
        # IDs iniciais padrão do banco de dados do PetClinic (1 a 10)
        owner_id = random.randint(1, 10)
        self.client.get(f"/api/customer/owners/{owner_id}", name="/api/customer/owners/[id]")

    def get_vets(self):
        self.client.get("/api/vet/vets", name="/api/vet/vets")

    def create_owner(self):
        uid = uuid.uuid4().hex[:6]
        payload = {
            "firstName": f"Locust{uid}",
            "lastName": f"User{uid}",
            "address": f"{random.randint(1, 999)} Main St",
            "city": "PerformanceCity",
            "telephone": f"{random.randint(1000000000, 9999999999)}"
        }
        headers = {"Content-Type": "application/json"}
        self.client.post("/api/customer/owners", json=payload, headers=headers, name="/api/customer/owners")


class ReadingUser(BasePetClinicUser):
   
    @task(45)
    def task_get_owners(self):
        self.get_owners()

    @task(35)
    def task_get_owner_by_id(self):
        self.get_owner_by_id()

    @task(15)
    def task_get_vets(self):
        self.get_vets()

    @task(5)
    def task_create_owner(self):
        self.create_owner()


class WritingUser(BasePetClinicUser):
 
    @task(20)
    def task_get_owners(self):
        self.get_owners()

    @task(20)
    def task_get_owner_by_id(self):
        self.get_owner_by_id()

    @task(20)
    def task_get_vets(self):
        self.get_vets()

    @task(40)
    def task_create_owner(self):
        self.create_owner()


# Permite selecionar perfil também via variável de ambiente LOAD_PROFILE=reading|writing
profile_env = os.getenv("LOAD_PROFILE", "").strip().lower()
if profile_env == "reading" or profile_env == "leitura":
    WritingUser.abstract = True
elif profile_env == "writing" or profile_env == "escrita":
    ReadingUser.abstract = True

