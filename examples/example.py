from stowrypy import StowryClient

client = StowryClient(
    endpoint="http://localhost:5708",
    access_key="FE373CEF5632FDED3081",
    secret_key="9218d0ddfdb1779169f4b6b3b36df321099e98e9",
)

# Generate presigned GET URL
get_url = client.presign_get("/files/document.pdf", expires=900)
print(f"GET URL: {get_url}")

# Generate presigned PUT URL
put_url = client.presign_put("/files/upload.txt", expires=900)
print(f"PUT URL: {put_url}")

# Generate presigned DELETE URL
delete_url = client.presign_delete("/files/old.txt", expires=900)
print(f"DELETE URL: {delete_url}")
