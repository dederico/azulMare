aws ecr get-login-password --profile callgpt --region us-east-1 | docker login --username AWS --password-stdin 414872280979.dkr.ecr.us-east-1.amazonaws.com

docker buildx build --platform linux/amd64 -t callgpt-demo .

docker tag callgpt-demo:latest 414872280979.dkr.ecr.us-east-1.amazonaws.com/callgpt-demo:latest

docker push 414872280979.dkr.ecr.us-east-1.amazonaws.com/callgpt-demo:latest

uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload