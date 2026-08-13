from typing import Optional

# The point of these exceptions is to provide more specific error messages which
# also embed the ID or name of the object that was not found. This is useful for
# debugging and logging purposes.


class LibraryNotFound(Exception):
    def __init__(self, name: Optional[str] = None, idnum: Optional[int] = None):
        self.lib_name = name
        self.lib_id = idnum

    def __str__(self):
        if self.lib_name:
            return f"Name: {self.lib_name}"
        return f"ID: {self.lib_id}"


class ModelNotFound(Exception):
    def __init__(self, name: Optional[str] = None, idnum: Optional[int] = None):
        self.model_name = name
        self.model_id = idnum

    def __str__(self):
        if self.model_name:
            return f"Name: {self.model_name}"
        return f"ID: {self.model_id}"


class ShapeCollectionNotFound(Exception):
    def __init__(self, name: Optional[str] = None, idnum: Optional[int] = None):
        self.shape_collection_name = name
        self.shape_collection_id = idnum

    def __str__(self):
        if self.shape_collection_name:
            return f"Name: {self.shape_collection_name}"
        return f"ID: {self.shape_collection_id}"


class TemplateNotFound(Exception):
    def __init__(self, name: Optional[str] = None, idnum: Optional[int] = None):
        self.template_name = name
        self.template_id = idnum

    def __str__(self):
        if self.template_name:
            return f"Name: {self.template_name}"
        return f"ID: {self.template_id}"


class TemplateDependencyNotFound(Exception):
    def __init__(self, idnum: int):
        self.template_dependency_id = idnum

    def __str__(self):
        return f"ID: {self.template_dependency_id}"


class KnowledgeDocumentNotFound(Exception):
    def __init__(self, idnum: int):
        self.document_id = idnum

    def __str__(self):
        return f"ID: {self.document_id}"
