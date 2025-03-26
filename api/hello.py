import json

def handler(request, response):
    # 设置CORS头
    response.headers = {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,OPTIONS,PATCH,DELETE,POST,PUT",
        "Access-Control-Allow-Headers": "X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version",
        "Content-Type": "application/json"
    }
    
    # 处理OPTIONS请求
    if request.method == "OPTIONS":
        return {"status": "success"}
    
    return {
        "status": "success",
        "message": "Hello World from Vercel Function",
        "path": request.path
    } 