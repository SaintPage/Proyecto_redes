# Imagen para desplegar el servidor MCP de farmacia de forma remota
# (funcionalidad 6). Sirve para Google Cloud Run, Render, Fly.io y
# cualquier plataforma que ejecute contenedores.
#
# El servidor no tiene dependencias externas: el protocolo MCP y el
# transporte HTTP estan implementados sobre la libreria estandar.

FROM python:3.12-slim

WORKDIR /app

# Solo se copia lo que el servidor necesita. El chatbot anfitrion, las
# pruebas y la documentacion no forman parte de la imagen.
COPY server/ ./server/
COPY data/ ./data/

# Las plataformas de nube inyectan PORT; 8080 es el valor por defecto
# y coincide con el que espera Cloud Run.
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "-m", "server.main_http"]
