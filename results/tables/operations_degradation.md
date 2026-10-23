# Degradação por Operação (Tempo Médio e P95)

| Perfil | Cenário | Operação | Tempo Médio (ms) | P95 (ms) | Total Reqs |
|:---|:---:|:---|:---:|:---:|:---:|
| Leitura | A (30u) | GET /api/customer/owners | 228.39 | 531.68 | 3,001 |
| Leitura | A (30u) | GET /api/customer/owners/[id] | 15.76 | 94.99 | 2,323 |
| Leitura | A (30u) | GET /api/vet/vets | 8.26 | 14.41 | 1,013 |
| Leitura | A (30u) | POST /api/customer/owners | 17.06 | 74.13 | 330 |
| Leitura | B (80u) | GET /api/customer/owners | 653.03 | 3266.11 | 6,665 |
| Leitura | B (80u) | GET /api/customer/owners/[id] | 521.53 | 3203.69 | 5,210 |
| Leitura | B (80u) | GET /api/vet/vets | 5.22 | 8.64 | 2,226 |
| Leitura | B (80u) | POST /api/customer/owners | 509.97 | 2846.75 | 746 |
| Leitura | C (150u) | GET /api/customer/owners | 327.95 | 1750.10 | 13,865 |
| Leitura | C (150u) | GET /api/customer/owners/[id] | 284.60 | 1670.20 | 10,721 |
| Leitura | C (150u) | GET /api/vet/vets | 5.00 | 8.17 | 4,585 |
| Leitura | C (150u) | POST /api/customer/owners | 280.41 | 1634.69 | 1,542 |
| Escrita | A (30u) | GET /api/customer/owners | 1585.09 | 4289.48 | 982 |
| Escrita | A (30u) | GET /api/customer/owners/[id] | 872.31 | 3828.66 | 1,012 |
| Escrita | A (30u) | GET /api/vet/vets | 5.14 | 7.96 | 999 |
| Escrita | A (30u) | POST /api/customer/owners | 891.66 | 3879.90 | 1,992 |
| Escrita | B (80u) | GET /api/customer/owners | 381.18 | 1556.55 | 3,322 |
| Escrita | B (80u) | GET /api/customer/owners/[id] | 258.35 | 1415.97 | 3,313 |
| Escrita | B (80u) | GET /api/vet/vets | 11.16 | 38.05 | 3,333 |
| Escrita | B (80u) | POST /api/customer/owners | 264.74 | 1376.80 | 6,693 |
| Escrita | C (150u) | GET /api/customer/owners | 172.31 | 5841.08 | 6,076 |
| Escrita | C (150u) | GET /api/customer/owners/[id] | 137.81 | 1327.82 | 6,060 |
| Escrita | C (150u) | GET /api/vet/vets | 57.56 | 1410.17 | 6,101 |
| Escrita | C (150u) | POST /api/customer/owners | 152.46 | 7199.88 | 12,128 |
