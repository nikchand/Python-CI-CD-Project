from fastapi import FastAPI

app = FastAPI()

books = {}

@app.get("/")
def root():
    return {"message": "Hello from FastAPI CI/CD!"}

@app.post("/books/{book_id}")
def create_book(book_id: int, title: str):
    books[book_id] = title
    return {"id": book_id, "title": title}

@app.get("/books")
def list_books():
    return books

@app.get("/books/{book_id}")
def get_book(book_id: int):
    return {"id": book_id, "title": books.get(book_id, "Not Found")}

@app.put("/books/{book_id}")
def update_book(book_id: int, title: str):
    books[book_id] = title
    return {"id": book_id, "title": title}

@app.delete("/books/{book_id}")
def delete_book(book_id: int):
    books.pop(book_id, None)
    return {"message": "Deleted"}
