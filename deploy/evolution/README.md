# Evolution API

Infraestrutura versionada da Evolution usada pelo VemDeDelivery.

- A imagem está fixada em `v2.3.7`; atualizações devem ser deliberadas e testadas em homologação.
- O `.env` real nunca deve ser versionado.
- A porta 8080 fica exposta apenas em `127.0.0.1`; o acesso público passa pelo Nginx do VemDeDelivery.
- A rede Docker criada por este compose se chama `evolution_evolution`, usada pelo Nginx de produção como rede externa.

No VPS atual, `/opt/evolution/docker-compose.yml` deve permanecer equivalente a este arquivo.
