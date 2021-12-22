"""
OpenAPI 3.0 Schema Objects
====================================
For official specs, see https://swagger.io/specification/
"""

from pydantic import BaseModel, Field, ValidationError
from pydantic.main import ModelMetaclass
from rest_framework import serializers
from typing import Optional, List, Dict, Union, Type, Any
from .utils import schema_set_examples, get_url_patterns

from .enums import (
    HttpMethod, 
    ViewAttributes,
    DjaggerAttributeEnumType,
    DJAGGER_HTTP_METHODS,
)

import uuid
import inspect
import warnings
import copy 

class Logo(BaseModel):
    """ Logo image for display on redoc documents. 
    """
    url : Optional[str]
    altText : Optional[str]

class ExternalDocs(BaseModel):
    description: Optional[str]
    url : str

class Tag(BaseModel):
    """ OpenAPI `tags` """
    name : str
    description : Optional[str]
    externalDocs : Optional[ExternalDocs]

class Contact(BaseModel):
    """ OpenAPI `contact` object"""
    name : Optional[str]
    url : Optional[str]
    email : Optional[str]

class License(BaseModel):
    """ OpenAPI `license` object"""
    name : str
    url : Optional[str]

class Info(BaseModel):

    """OpenAPI document information"""

    title : str = "Djagger OpenAPI 3.0 Documentation"
    description : str = "OpenAPI 3.0 Document Description"
    termsOfService : Optional[str]
    contact : Optional[Contact]
    license : Optional[License]
    version : str = "1.0.0"
    x_logo : Optional[Logo] = Field(alias="x-logo") #reDoc

    class Config:
        allow_population_by_field_name = True


class TagGroup(BaseModel):
    """ Tag grouping for ``x-tagGroups`` setting in redoc. 
    This beyond the OpenAPI 3.0 specs but is included for redoc.
    """
    name : str 
    tags : List[str] 


class ServerVariable(BaseModel):

    enum : Optional[List[str]] 
    default : str
    description : Optional[str]

class Server(BaseModel):

    url : str
    description : Optional[str]
    variables : Optional[Dict[str, ServerVariable]]

class Reference(BaseModel):

    ref_ : str = Field(alias="$ref")

    def ref_name(self):
        # Assuming reference has default ref_template 
        # '#/definitions/{model}'
        return self.ref_.split("/")[-1]
    
    @classmethod
    def to_ref(cls, obj : Any) -> Union['Reference', None]:
        # Check if variable is a valid dict representation of Ref
        # if valid, returns an instance of the Ref
        if isinstance(obj, Dict):
            try:
                return cls(**obj)
            except (TypeError, ValidationError):
                return None
        return None

    @classmethod
    def dereference(cls, schema : Union[Dict, List], definitions: Dict) -> Dict:
        """Recursively converts all references within a schema into the actual referenced object. 
        The resulting schema is the same one without any references.
        """
        if isinstance(schema, Dict):
            for k, v in schema.items():
                ref = cls.to_ref(v)
                if ref:
                    ref_obj = definitions.get(ref.ref_name(), {})
                    schema[k] = cls.dereference(ref_obj, definitions)
                    
                elif isinstance(v, Dict) or isinstance(v, List):
                    schema[k] = cls.dereference(v, definitions)

        if isinstance(schema, List):
            
            for i in range(len(schema)):
                ref = cls.to_ref(schema[i])
                if ref:
                    ref_obj = definitions.get(ref.ref_name(), {})
                    schema[i] = cls.dereference(ref_obj, definitions)
                    
                elif isinstance(schema[i], Dict) or isinstance(schema[i], List):
                    schema[i] = cls.dereference(schema[i], definitions)

        return schema

    class Config:
        allow_population_by_field_name = True

class Example(BaseModel):
    
    summary : Optional[str]
    description : Optional[str]
    value : Optional[Any]
    externalValue : Optional[str]

class Link(BaseModel):

    operationRef : Optional[str]
    operationId : Optional[str]
    parameters : Optional[Dict[str, Any]]
    requestBody : Optional[Any]
    description : Optional[str]
    server : Optional[Server]


class OAuthFlow(BaseModel):

    authorizationUrl : str
    tokenURL : str
    refreshURL : Optional[str]
    scopes : Dict[str, str]


class OAuthFlows(BaseModel):
    implicit : Optional[OAuthFlow]
    password : Optional[OAuthFlow]
    clientCredentials : Optional[OAuthFlow]
    authorizationCode : Optional[OAuthFlow]


SecurityRequirement = Dict[str, List[str]]


class SecurityScheme(BaseModel):
    
    type_ : str = Field(alias="type")
    description : Optional[str]
    name : str
    in_ : str = Field(alias="in")
    scheme : str 
    bearerFormat : Optional[str]
    flows : OAuthFlows 
    openIdConnectUrl : str

Callback = Dict[str, 'Path']

class Header(BaseModel):
    """ The Header Object follows the structure of the Parameter Object with the following changes:
    1. ``name`` MUST NOT be specified, it is given in the corresponding headers map.
    2. ``in`` MUST NOT be specified, it is implicitly in header.
    3. All traits that are affected by the location MUST be applicable to a location of header (for example, style).
    """
    description : Optional[str]
    required : bool = False
    deprecated : bool = False
    allowEmptyValue : bool = False
    style : Optional[str]
    explode : bool = False
    allowReserved : bool = False
    schema_ : Optional[Union[Dict, Reference]] = Field(alias="schema") # schema can take in a `.schema()` dict value from pydantic
    example : Optional[Any]
    examples : Optional[Dict[str, Union[Example, Reference]]]
    content : Optional[Dict[str, 'MediaType']] # For more complex values - unused for now.

    class Config:
        allow_population_by_field_name = True

class Encoding(BaseModel):
    
    contentType : Optional[str]
    headers : Optional[Dict[str, Union[Header, Reference]]]
    style : Optional[str]
    explode : bool = False
    allowReserved : bool = False    

class MediaType(BaseModel):

    schema_ : Optional[Union[Dict, Reference]] = Field(alias="schema") # schema can take in a `.schema()` dict value from pydantic
    example : Optional[Any]
    examples : Optional[Dict[str, Union[Example, Reference]]]
    encoding : Optional[Dict[str, Encoding]]

    class Config:
        allow_population_by_field_name = True
    
    @classmethod
    def _from(cls, model : ModelMetaclass) -> 'MediaType':
        """Generates an instance of MediaType from a pydantic model"""
        
        media = cls()
        schema = model.schema()
        schema = schema_set_examples(schema, model)

        definitions = schema.pop('definitions', {})
        if not definitions:
            media.schema_ = schema
        else:
            media.schema_ = Reference.dereference(schema, definitions)
        
        # Generate example
        if hasattr(model, 'example'):
            if callable(model.example):
                media.example = model.example().dict(by_alias=True, exclude_none=True)

        # TODO: Handle multiple examples for ``examples`` field
        
        # Look for ``encoding`` in model Config and instantiate it 
        encoding = getattr(model.Config, 'encoding', {})

        if not isinstance(encoding, Dict):
            raise TypeError('encoding in model Config needs to be a Dict')

        if encoding:
            # TODO: validation for internals of ``encoding``
            media.encoding = encoding

        return media

class Parameter(BaseModel):
    name : str
    in_ : str = Field(alias="in")
    description : Optional[str]
    required : bool = False
    deprecated : bool = False
    allowEmptyValue : bool = False
    style : Optional[str]
    explode : bool = False
    allowReserved : bool = False
    schema_ : Optional[Union[Dict, Reference]] = Field(alias="schema") # schema can take in a `.schema()` dict value from pydantic
    example : Optional[Any]
    examples : Optional[Dict[str, Union[Example, Reference]]]
    content : Optional[Dict[str, MediaType]] # For more complex values - unused for now.

    class Config:
        allow_population_by_field_name = True

    @classmethod
    def to_parameters(cls, model : ModelMetaclass, attr : DjaggerAttributeEnumType) -> List['Parameter']:
        """ Converts the fields of a pydantic model to list of Parameter objects for use in generating request parameters.
        All attribute names ending in '_params' are relevant here. Non parameter object attributes should not be passed
        """
        params = []

        if "_params" not in attr.value:
            raise AttributeError("`to_parameters` only accepts parameter attributes ending with '_param'")

        if not isinstance(attr, DjaggerAttributeEnumType):
            raise TypeError("attr must be an enum of DjaggerAttributeEnumType type")

        if not isinstance(model, ModelMetaclass):
            raise TypeError("Parameter object must be pydantic.main.ModelMetaclass type")

        if attr == attr.BODY_PARAMS:
            # Request body handled by extract_request_body()
            return params
        
        # Handle parameters - path / query / header/ cookie 
        # with each field as a separate parameter in the list of parameters
        
        schema = model.schema()
        schema = schema_set_examples(schema, model)
        definitions = schema.pop('definitions', {})
        if definitions:
           schema = Reference.dereference(schema, definitions)

        properties = schema.get('properties',{})

        for name, props in properties.items():
            param = cls(
                name=name,
                description=props.get('description'),
                in_=attr.location(),
                required=props.get('required', False),
                deprecated=props.get('deprecated', False),
                allowReserved=props.get('allowReserved', False),
                style=props.get('style'),
                explode=props.get('explode', False),
                example=props.get('example'),
                examples=props.get('examples'),
                content=props.get('content'),
                schema_=props.get('schema')
            )
            params.append(param)
        
        return params

class RequestBody(BaseModel):
    description : Optional[str]
    content : Dict[str, MediaType] = {}
    required : bool = False

class Response(BaseModel):
    description : str = ""
    headers : Optional[Dict[str, Union[Header, Reference]]]
    content : Optional[Dict[str, MediaType]]
    links : Optional[Dict[str, Union[Link, Reference]]]

    @classmethod
    def _from(cls, model : ModelMetaclass) -> 'Response':
        # By default if a pydantic model is passed, the only content type is application/json for MediaType
        # to allow multiple content in a Response object, a python dict needs to be passed manually.
        # via Response.parse_obj(my_dict)
        response = cls(
            description=model.__doc__ if model.__doc__ else '',
            content={
                "application/json":MediaType._from(model)
            }
        )

        # Extract headers dict in the Response model Config
        headers = getattr(model.Config, 'headers', {})
        if headers and isinstance(headers, Dict):
            response.headers = {}
            for k, v in headers:
                try:
                    response.headers[k] = Header.parse_obj(v)
                except ValidationError as e:
                    warnings.warn(f"Validation error in header: {str(e)}")

        return response

Responses = Dict[str, Response]

class Operation(BaseModel):
    
    tags : Optional[List[str]]
    summary : Optional[str]
    description : Optional[str]
    externalDocs : Optional[ExternalDocs]
    operationId : Optional[str]
    parameters : List[Union[Parameter, Reference]] = []
    requestBody : Optional[Union[RequestBody, Reference]]
    responses: Responses = {}
    callbacks : Optional[Dict[str, Union[Callback, Reference]]] # TODO: callbacks Not implemented yet
    deprecated : bool = False
    security : Optional[List[SecurityRequirement]]
    servers : Optional[List[Server]]

        
    def _extract_operation_id(self, view : Type, http_method: HttpMethod):

        operation_id = ViewAttributes.from_view(view, 'operation_id', http_method)
        assert isinstance(operation_id, (str, type(None))), "operation_id must be string type"
        self.operationId = operation_id


    def _extract_external_docs(self, view : Type, http_method: HttpMethod):

        self.externalDocs = ViewAttributes.from_view(view, 'external_docs', http_method)
        assert isinstance(self.externalDocs, (Dict, type(None))), "externalDocs attribute needs to be a dict"

        if self.externalDocs:
            self.externalDocs = ExternalDocs.parse_obj(self.externalDocs)

    def _extract_parameters(self, view : Type, http_method: HttpMethod):
        """ Helper to initialize request `parameters` from a View for a given http method
        """

        self.parameters = []

        for attr in ViewAttributes.api.__members__.values():
            
            if "_params" not in attr:
                # only consider relevant for parameter attributes - attr name ending in '_params'
                continue

            request_schema = ViewAttributes.from_view(view, attr.value, http_method)
            if not request_schema:
                continue

            # Converting serializers to pydantic models
            if isinstance(request_schema, serializers.SerializerMetaclass):
                request_schema = SerializerConverter(s=request_schema()).to_model()

            self.parameters += Parameter.to_parameters(request_schema, attr)

    def _extract_tags(self, view : Type, http_method: HttpMethod):

        tags = ViewAttributes.from_view(view, 'tags', http_method)

        if not tags:
            tags = [view.__module__.split(".")[0]] # Set tags as the app module name of the API as fallback

        if tags:
            assert isinstance(tags, List), "tags attribute must be a list of strings"
            self.tags = tags

    def _extract_summary(self, view : Type, http_method: HttpMethod):

        summary = ViewAttributes.from_view(view, 'summary', http_method)

        if not summary:
            summary = view.__name__     

        if summary:
            assert isinstance(summary, str), "summary must be string type"
            self.summary = summary


    def _extract_description(self, view : Type, http_method: HttpMethod):

        description = ViewAttributes.from_view(view, 'description', http_method)

        if not description:
            description = view.__doc__

        if description:
            assert isinstance(description, str), "description must be string type"
            self.description = description


    def _extract_request_body(self, view : Type, http_method: HttpMethod):
        """ Extracts ``requestBody`` from the ``<http_method>_BODY_PARAMS`` attribute from the view.
        ``<http_method>_BODY_PARAMS`` value can be of the following types:
            - ``ModelMetaclass``
            - ``Dict[str, Union[ModelMetaclass, Dict]``
        """

        request_body = ViewAttributes.from_view(view, 'body_params', http_method)
        if not request_body: 
            return

        # Case where a pydantic model is passed, assumes only one media type i.e. application/json
        if isinstance(request_body, ModelMetaclass):
            self.requestBody = RequestBody(
                description = request_body.__doc__,
                content={
                    "application/json":MediaType._from(request_body)
                }
            )
            return 
        
        # Case where a dict is passed, extract ``required`` and ``description``
        # and media type for each pair in dict
        # E.g. 
        # {
        #     'description':'multiple request bodies',
        #     'required':False,
        #     'application/json': Schema_1,
        #     'text/plain': Schema_2 
        # }
        elif isinstance(request_body, Dict):

            body = RequestBody()
            body.description = request_body.pop('description', '')
            body.required = request_body.pop('required', False)
            content = {}
            for k, v in request_body.items():
                if isinstance(v, Dict):
                    # validate for MediaType if a dict is given as the value of content
                    content[k] = MediaType(**v)

                elif isinstance(v, ModelMetaclass):
                    content[k] = MediaType._from(v) 

                else:
                    raise TypeError(f"Value in request body dict must be a Dict type or pydantic ModelMetaclass. Got {type(v)}")
                
            body.content = content

            self.requestBody = body
            return

        raise TypeError(f"Request body needs to be of type Dict or pydantic ModelMetaclass. Got {type(request_body)}")


    def _extract_responses(self, view : Type, http_method: HttpMethod):
        """ Helper to initialize `responses` from a view class and returns responses dict for EndPoint
        """
        if not isinstance(http_method, HttpMethod):
            raise TypeError("http_method is not a valid HttpMethod type")

        responses = {}

        response_schema = ViewAttributes.from_view(view, 'response_schema', http_method)

        # When attribute is a pydantic model - assume 200 response only
        if isinstance(response_schema, ModelMetaclass):
            responses = { 
                '200': Response._from(response_schema)
            }
        # When attribute is a Serializer - assume 200 response only
        elif isinstance(response_schema, serializers.SerializerMetaclass):
            responses = {
                '200': Response._from(SerializerConverter(s=response_schema()).to_model())
            }
        # When attribute is a dict of responses, prepare dict of Response values
        elif isinstance(response_schema, Dict):

            for status_code, model in response_schema.items():
                if not isinstance(status_code, str):
                    raise ValueError("key in response schema dict needs to be string")

                if isinstance(model, serializers.SerializerMetaclass):
                    model = SerializerConverter(s=model()).to_model()
                    responses[status_code] = Response._from(model)

                elif isinstance(model, Dict):
                    # For manual parsing if a Dict is passed instead of the expected ModelMetaclass or Serializer
                    responses[status_code] = Response.parse_obj(model)
                
                else:
                    responses[status_code] = Response._from(model)
        
        self.responses = responses
        

    def _extract_security(self, view : Type, http_method: HttpMethod):

        self.security = ViewAttributes.from_view(view, 'security', http_method)
        assert isinstance(self.servers, (List, type(None))), "security attribute needs to be a list of objects"

        if self.security:
            for security in self.security:
                assert isinstance(security, Dict), "security items need to be dict of list of strings"
                for k, v in security.items():
                    assert isinstance(k, str), "security requirement key needs to be a string"
                    assert isinstance(v, List), "security requirement value needs to be list of strings"
                    for m in v:
                        assert isinstance(m, str), "security requirement value needs to be a list of strings"

    def _extract_servers(self, view : Type, http_method: HttpMethod):

        self.servers = ViewAttributes.from_view(view, 'servers', http_method)
        assert isinstance(self.servers, (List, type(None))), "servers attribute needs to be a list of server objects"
        if self.servers:
            self.servers = [ Server.parse_obj(server) for server in self.servers ]

    def _extract_deprecated(self, view : Type, http_method: HttpMethod):

        self.deprecated = ViewAttributes.from_view(view, 'deprecated', http_method)
        assert isinstance(self.deprecated, (bool, type(None))), "deprecated attribute needs to be boolean"

    @classmethod
    def _from(cls, view : Type, http_method : HttpMethod) -> Union['Operation', None]:
        """ Extract attributes from a view class to instantiate Operation given the type of http method for the Operation.
        Wil return None if exclude attribute is True.
        """
        
        operation = cls(
            tags = [],
            summary = "",
            description = "",
            parameters = [],
            responses = {}
        )

        # Exclude at the method-level if `<http_method>_djagger_exclude` is True
        exclude = ViewAttributes.from_view(view, 'djagger_exclude', http_method)
        if exclude:
            return None

        operation._extract_tags(view, http_method)
        operation._extract_operation_id(view, http_method)
        operation._extract_deprecated(view, http_method)
        operation._extract_security(view, http_method)
        operation._extract_servers(view, http_method)
        operation._extract_external_docs(view, http_method)
        operation._extract_summary(view, http_method)
        operation._extract_description(view, http_method)
        operation._extract_request_body(view, http_method)
        operation._extract_parameters(view, http_method)
        operation._extract_responses(view, http_method)

        return operation



class Path(BaseModel):

    summary : Optional[str]
    description : Optional[str]
    get : Optional[Operation]
    put : Optional[Operation]
    post : Optional[Operation]
    delete : Optional[Operation]
    options : Optional[Operation]
    head : Optional[Operation]
    patch : Optional[Operation]
    trace : Optional[Operation]
    servers : Optional[List[Server]] # Not implemented - Done at operation level
    parameters : List[Union[Parameter, Reference]] = [] # Not implemented - Done at operation level
    ref_ : Optional[str] = Field(alias="$ref") # Not implemented

    class Config:
        allow_population_by_field_name = True

    @classmethod
    def create(cls, view : Type) -> 'Path':
        """ Given a Class-based view or a function based view, create the Path object 
        from the Djagger attributes set in the view.
        """
        path = cls(
            summary = getattr(view, 'summary', None),
            description = getattr(view, 'description', None)
        )
        
        if inspect.isclass(view):
            # For CBV or DRF API, check for methods by looking for get(), post(), patch(), put(), delete() methods
            for http_method in HttpMethod.__members__.values():
                if hasattr(view, http_method):
                    if callable(getattr(view, http_method)):
                        operation = Operation._from(view, http_method)
                        if not operation:
                            continue

                        setattr(path, http_method, operation)

        elif inspect.isfunction(view):

            # Handle DRF ViewSets 
            # DRF ViewSets are function based views with an ``actions`` attr which is a dict
            # of http_methods as keys. 

            # TODO: Handle each ViewSet function with separate schemas, treating each function
            # `retrieve`, `list` etc. as one FBV each
            
            if hasattr(view, 'actions'):
                for k in view.actions.keys():
                    try:
                        http_method = HttpMethod(k)
                    except ValueError:
                        continue

                    operation = Operation._from(view, http_method)
                    if not operation:
                        continue
                    if not operation.responses:
                        continue
                    setattr(path, http_method, operation)

            # For FBVs, check for existence of http methods from the `djagger_http_methods` attribute
            # set by the @schema decorator

            if not hasattr(view, DJAGGER_HTTP_METHODS):
                return path

            for method in getattr(view, DJAGGER_HTTP_METHODS, []):
                http_method = HttpMethod(method.lower())
                operation = Operation._from(view, http_method)
                if not operation:
                    continue
                if not operation.responses:
                    continue
                setattr(path, http_method, operation)

        return path


Paths = Dict[str, Path]

class Components(BaseModel):
    # Replaces Definitions in Swagger 2.0

    schemas : Dict[str, Dict] = {}
    responses : Dict[str, Union[Response, Reference]] = {}
    parameters : Dict[str, Union[Parameter, Reference]] = {}
    examples : Dict[str, Union[Example, Reference]] = {}
    requestBodies : Dict[str, Union[RequestBody, Reference]] = {}
    headers : Dict[str, Union[Header, Reference]] = {}
    securitySchemes : Dict[str, Union[SecurityScheme, Reference]] = {}
    links : Dict[str, Union[Link, Reference]] = {}
    callbacks : Dict[str, Union[Callback, Reference]] = {}

    def merge(self, component : 'Components'):
        """Copy the contents of another ``Components`` instance and merge it into this instance"""
        
        for field in self.__fields__.keys():
            getattr(self, field).update(copy.deepcopy(getattr(component, field)))

class Document(BaseModel):

    openapi : str = "3.0.0"
    info : Info = Info()
    servers : List[Server] = []
    paths : Paths = {}
    components : Components = Components()
    security : List[SecurityRequirement] = []
    tags : List[Tag] = []
    externalDocs : Optional[ExternalDocs]

    @classmethod
    def generate(
        cls,
        app_names : List[str] = [],
        tags : List[Tag] = [],
        openapi = "3.0.0",
        version = "1.0.0",
        servers : List[Server] = [],
        security : List[SecurityRequirement] = [],
        title = "Djagger OpenAPI Documentation",
        description = "",
        terms_of_service = "",
        contact_name = None,
        contact_email = "",
        contact_url = "",
        license_name = "",
        license_url = "",
        x_tag_groups : List[TagGroup]= []
    ) -> dict :
        """ Inspects URLPatterns in given list of apps to generate the openAPI json object for the Django project.
        Returns the JSON string object for the resulting OAS document.
        """

        url_patterns = get_url_patterns(app_names)
        paths : Dict[str, Path] = {}

        for route, url_pattern in url_patterns:

            try:
                view = url_pattern.callback.view_class # Class-based View
            except AttributeError:
                view = url_pattern.callback # Function-based View / ViewSet 
            
            if ViewAttributes.from_view(view, 'djagger_exclude'):
                continue
            
            path = Path.create(view)

            # If path has none of the methods documented, skip its documentation
            if getattr(path, 'get', None) or \
                getattr(path, 'post', None) or \
                getattr(path, 'put', None) or \
                getattr(path, 'patch', None) or \
                getattr(path, 'delete', None):

                    paths["/" + route] = path


        # Create tag objects as provided
        # Note that if tags supplied is empty, they will still be generated when
        # set as attributes in the individual API or endpoints
        tags = [
            Tag(name=tag["name"], description=tag.get("description","")) for tag in tags
        ]
        info = Info(
            description=description,
            version=version,
            title=title,
            termsOfService=terms_of_service,
            contact=Contact(
                name=contact_name,
                email=contact_email,
                url=contact_url
            ),
            license=License(
                name=license_name,
                url=license_url
            ),
        )
        document = cls(
            openapi=openapi,
            info=info,
            servers=servers,
            tags=tags,
            paths=paths,
            x_tag_groups=x_tag_groups,
        )

        return document.dict(by_alias=True, exclude_none=True)
