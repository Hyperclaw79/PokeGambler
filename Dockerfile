FROM python:3.9.6-slim
WORKDIR /usr/bot
COPY . ./
RUN pip install --no-cache-dir -r requirements.txt
CMD [ "python3", "launcher.py" ]