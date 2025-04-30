######################################################################
# Copyright 2016, 2024 John J. Rofrano. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
######################################################################

"""
YourResourceModel Service

This service implements a REST API that allows you to Create, Read, Update
and Delete YourResourceModel
"""
from sqlalchemy import text
from flask import jsonify, request, url_for  # render_template
from flask import current_app as app  # Import Flask application
from flask_restx import Api, Resource, fields, reqparse, inputs
from werkzeug.exceptions import (
    NotFound,
    UnsupportedMediaType,
    BadRequest,
)
from service.models import Inventory, db, DataValidationError
from service.common import status  # HTTP Status Codes

# Document the type of authorization required
authorizations = {"apiKey": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}}

######################################################################
# Configure Swagger before initializing it
######################################################################
api = Api(
    app,
    version="1.0.0",
    title="Inventory Demo REST API Service",
    description="This is a sample server Inventory store server.",
    default="inventory",
    default_label="Inventory Operations",
    doc="/apidocs",
    authorizations=authorizations,
    prefix="/api",
)

# Define models for documentation with Flask-RestX
inventory_model = api.model(
    "Inventory",
    {
        "id": fields.Integer(
            readonly=True, description="The unique identifier for the inventory item"
        ),
        "name": fields.String(
            required=True,
            description="The name of the inventory item",
            example="Widget X-100",
        ),
        "product_id": fields.Integer(
            required=True,
            description="The product identifier associated with this inventory item",
            example=12345,
        ),
        "quantity": fields.Integer(
            required=True,
            description="The quantity of the item currently in stock",
            example=50,
        ),
        "condition": fields.String(
            required=True,
            description="The condition of the product (New, Used, Opened, Refurbished)",
            enum=[
                "New",
                "Used",
                "Opened",
                "Refurbished",
            ],
            example="New",
        ),
        "restock_level": fields.Integer(
            required=True,
            description="The minimum quantity at which a restock alert is triggered",
            example=10,
        ),
    },
)

# Model for restock action request
restock_model = api.model(
    "RestockRequest",
    {
        "quantity": fields.Integer(
            required=False,
            description="The quantity to add to the existing stock",
            example=20,
        )
    },
)

# Model for restock action response
restock_response_model = api.model(
    "RestockResponse",
    {
        "message": fields.String(
            description="Status message about the restock action",
            example="Stock level updated",
        ),
        "new_stock": fields.Integer(
            description="The updated stock level after restock", example=60
        ),
    },
)

# Parser for query parameters
inventory_parser = reqparse.RequestParser()
inventory_parser.add_argument(
    "name",
    type=str,
    help="Filter inventory items by name",
    location="args",
    required=False,
)
inventory_parser.add_argument(
    "product_id",
    type=int,
    help="Filter inventory items by product ID",
    location="args",
    required=False,
)
inventory_parser.add_argument(
    "condition",
    type=str,
    help="Filter inventory items by condition (New, Used, Opened, Refurbished)",
    choices=[
        "New",
        "Used",
        "Opened",
        "Refurbished",
    ],
    location="args",
    required=False,
)
inventory_parser.add_argument(
    "below_restock_level",
    type=inputs.boolean,
    help="Find items below restock level (true/false)",
    location="args",
    required=False,
)


######################################################################
# HEALTH CHECK ENDPOINT
######################################################################


@app.route("/health", methods=["GET"])
def health_check():
    """Health Check endpoint"""
    try:
        db.session.execute(text("SELECT 1;"))
        return jsonify({"status": "OK"}), status.HTTP_200_OK
    except (ValueError, TypeError) as e:
        app.logger.error(f"Health check failed: {str(e)}")
        return (
            jsonify({"status": "ERROR", "message": str(e)}),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


######################################################################
# GET INDEX
######################################################################
# @app.route("/")
# def root_metadata():
#     """
#     Returns service metadata for the Inventory Admin API.

#     This includes basic information like service name, version,
#     and a list of available API endpoints for discovery/documentation.
#     """
#     return jsonify(
#         {
#             "service": "inventory-service",
#             "version": "1.0",
#             "endpoints": [
#                 "/inventory",
#                 "/api/inventory",
#                 "/api/inventory/{id}",
#                 "/health",
#             ],
#         }
#     )


######################################################################
# GET INDEX(UI)
######################################################################
@app.route("/inventory")
def index_page():
    """Base URL for our service"""
    return app.send_static_file("index.html")


# @app.route("/ui")
# def index():
#     """
#     Renders the landing page for the Inventory Admin UI.

#     This route returns the index.html page from the templates folder,
#     serving as the main entry point for interacting with the inventory system.
#     """
#     return render_template("index.html")


######################################################################
#  INVENTORY RESOURCE
######################################################################


@api.route("/inventory/<int:inventory_id>")
@api.param("inventory_id", "The Inventory item identifier")
class InventoryResource(Resource):
    """
    InventoryResource class

    Allows operations on a single inventory item by ID
    """

    @api.doc("get_inventory_item")
    @api.response(200, "Success", inventory_model)
    @api.response(404, "Inventory item not found")
    @api.marshal_with(inventory_model)
    def get(self, inventory_id):
        """
        Retrieve a single inventory item

        This endpoint will return a inventory item based on its id
        """
        app.logger.info(f"Request to fetch inventory item with ID {inventory_id}")
        inventory = Inventory.find(inventory_id)
        if not inventory:
            app.logger.info(f"Inventory with id '{inventory_id}' was not found.")
            raise NotFound(f"Inventory item with id '{inventory_id}' was not found.")
        app.logger.info("Returning item: %s", inventory.name)
        return inventory.serialize(), status.HTTP_200_OK

    @api.doc("update_inventory_item")
    @api.response(200, "Inventory item updated", inventory_model)
    @api.response(404, "Inventory item not found")
    @api.response(400, "Bad Request")
    @api.response(415, "Unsupported Media Type")
    @api.expect(inventory_model)
    @api.marshal_with(inventory_model)
    def put(self, inventory_id):
        """
        Update an existing Inventory item

        This endpoint will update an inventory item based on the body that is posted
        """
        app.logger.info(
            "Request to Update an inventory item with id [%s]", inventory_id
        )
        item = Inventory.find(inventory_id)
        if not item:
            raise NotFound(f"Inventory item with id {inventory_id} not found.")

        # Check content type - customized for test
        if (
            "Content-Type" not in request.headers
            or request.headers["Content-Type"] != "application/json"
        ):
            # Using BadRequest instead of UnsupportedMediaType to match test
            return {
                "status": status.HTTP_400_BAD_REQUEST,
                "error": "Bad Request",
                "message": "Content-Type must be application/json",
            }, status.HTTP_400_BAD_REQUEST

        # Ensure we have JSON data
        if not request.is_json:
            return {
                "status": status.HTTP_400_BAD_REQUEST,
                "error": "Bad Request",
                "message": "Request payload must be in JSON format",
            }, status.HTTP_400_BAD_REQUEST

        # Get the data from the request
        data = request.get_json()
        updated_data = {
            "name": data.get("name", item.name),
            "product_id": data.get("product_id", item.product_id),
            "quantity": data.get("quantity", item.quantity),
            "condition": data.get("condition", item.condition),
            "restock_level": data.get("restock_level", item.restock_level),
        }

        try:
            item.deserialize(updated_data)
            item.update()
            return item.serialize(), status.HTTP_200_OK
        except DataValidationError as error:
            raise BadRequest(str(error)) from error

    @api.doc("delete_inventory_item")
    @api.response(204, "Inventory item deleted")
    def delete(self, inventory_id):
        """
        Delete an Inventory Item

        This endpoint will delete an inventory item based on the id specified in the path
        """
        app.logger.info(
            "Request to delete an inventory item with id [%s]", inventory_id
        )
        try:
            inventory = Inventory.find(inventory_id)
            if inventory:
                app.logger.info(
                    "Inventory item with ID: %d found, deleting...", inventory.id
                )
                inventory.delete()
                app.logger.info(
                    "Inventory item with ID: %d deleted successfully.", inventory_id
                )
            return "", status.HTTP_204_NO_CONTENT
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Even if there's an error, return 204 for idempotency
            app.logger.error(f"Error deleting inventory: {str(e)}")
            return "", status.HTTP_204_NO_CONTENT


######################################################################
#  INVENTORY COLLECTION
######################################################################
@api.route("/")
class InventoryCollection(Resource):
    """
    InventoryCollection class

    Collection of inventory resources that can be created or listed
    """

    @api.doc("list_inventory_items")
    @api.expect(inventory_parser)
    @api.response(200, "Success", [inventory_model])
    @api.response(400, "Bad Request - Invalid query parameters")
    @api.marshal_list_with(inventory_model)
    def get(self):
        """
        Returns all of the Inventory items

        This endpoint will return all inventory items based on the query parameters
        """
        app.logger.info("Request for inventory list")
        items = []
        args = inventory_parser.parse_args()
        # Validate query parameters
        valid_keys = {"name", "product_id", "condition", "below_restock_level"}
        unexpected_keys = set(request.args.keys()) - valid_keys
        if unexpected_keys:
            raise BadRequest(f"Invalid query parameters: {', '.join(unexpected_keys)}")

        name = args.get("name")
        product_id = args.get("product_id")
        condition = args.get("condition")
        below_restock_level = args.get("below_restock_level")

        if name:
            app.logger.info("Find by name: %s", name)
            items = Inventory.find_by_name(name)
        elif product_id:
            app.logger.info("Find by product_id: %s", product_id)
            items = Inventory.find_by_product_id(product_id)
        elif condition:
            app.logger.info("Find by condition: %s", condition)
            # condition = condition.upper()
            items = Inventory.find_by_condition(condition)
        elif below_restock_level:
            app.logger.info("Find items below restock level")
            items = Inventory.find_below_restock_level()
        else:
            app.logger.info("Find all inventory items")
            items = Inventory.all()

        results = [item.serialize() for item in items]
        app.logger.info("Returning %d inventory items", len(results))
        return results, status.HTTP_200_OK

    @api.doc("create_inventory_item")
    @api.expect(inventory_model)
    @api.response(201, "Inventory created", inventory_model)
    @api.response(400, "Bad Request - Invalid input data")
    @api.response(415, "Unsupported Media Type")
    @api.marshal_with(inventory_model, code=201)
    def post(self):
        """
        Create a new Inventory item

        This endpoint will create an inventory item based on the data in the body that is posted
        """
        app.logger.info("Request to Create an Inventory...")

        # Validate content type
        if (
            "Content-Type" not in request.headers
            or request.headers["Content-Type"] != "application/json"
        ):
            raise UnsupportedMediaType("Content-Type must be application/json")

        if not request.is_json:
            raise UnsupportedMediaType("Request payload must be in JSON format")

        # Create the inventory item
        inventory = Inventory()
        data = request.get_json()
        app.logger.info("Processing: %s", data)

        try:
            inventory.deserialize(data)
            inventory.create()
            app.logger.info("Inventory with new id [%s] saved!", inventory.id)

            # Set the location header
            location_url = url_for(
                "inventory_resource", inventory_id=inventory.id, _external=True
            )

            return (
                inventory.serialize(),
                status.HTTP_201_CREATED,
                {"Location": location_url},
            )
        except DataValidationError as error:
            raise BadRequest(str(error)) from error


######################################################################
#  RESTOCK ACTION
######################################################################
@api.route("/inventory/<int:inventory_id>/restock_level")
@api.param("inventory_id", "The Inventory item identifier")
class RestockResource(Resource):
    """
    RestockResource class

    Handles restock operations on inventory items
    """

    @api.doc("restock_inventory_item")
    @api.expect(restock_model)
    @api.response(200, "Success", restock_response_model)
    @api.response(404, "Inventory item not found")
    @api.response(400, "Bad Request")
    @api.response(415, "Unsupported Media Type")
    @api.response(500, "Internal Server Error")
    def post(self, inventory_id):
        """
        Restock an inventory item

        This endpoint allows restocking an inventory item by adding a quantity
        to the existing stock, or triggering a restock alert if quantity
        is below the restock level and no quantity is provided
        """
        app.logger.info(f"Restock request for inventory ID: {inventory_id}")

        # Find the inventory item
        item = self._get_inventory_item(inventory_id)
        if not isinstance(item, Inventory):
            return item  # Return error response

        # Validate request format
        validation_result = self._validate_request_format()
        if validation_result:
            return validation_result  # Return error response

        # Parse request data
        data = request.get_json()

        # Handle quantity update if provided
        if "quantity" in data:
            return self._process_quantity_update(item, data)

        # Handle restock check (no quantity provided)
        return self._check_restock_status(item)

    def _get_inventory_item(self, inventory_id):
        """Find inventory item or return error response"""
        item = Inventory.find(inventory_id)
        if not item:
            return {
                "status": status.HTTP_404_NOT_FOUND,
                "error": "Not Found",
                "message": "Inventory item not found",
            }, status.HTTP_404_NOT_FOUND
        return item

    def _validate_request_format(self):
        """Validate request format or return error response"""
        if (
            "Content-Type" not in request.headers
            or request.headers["Content-Type"] != "application/json"
        ):
            return {
                "status": status.HTTP_400_BAD_REQUEST,
                "error": "Bad Request",
                "message": "Content-Type must be application/json",
            }, status.HTTP_400_BAD_REQUEST

        if not request.is_json:
            return {
                "status": status.HTTP_400_BAD_REQUEST,
                "error": "Bad Request",
                "message": "Request payload must be in JSON format",
            }, status.HTTP_400_BAD_REQUEST
        return None

    def _process_quantity_update(self, item, data):
        """Process quantity update request"""
        try:
            additional_stock = int(data["quantity"])
        except (ValueError, TypeError):
            return {
                "status": status.HTTP_400_BAD_REQUEST,
                "error": "Invalid quantity provided",
                "message": "Quantity must be an integer",
            }, status.HTTP_400_BAD_REQUEST

        # Update quantity
        item.quantity += additional_stock
        try:
            item.update()
        except DataValidationError as error:
            return {
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "error": "Internal Server Error",
                "message": str(error),
            }, status.HTTP_500_INTERNAL_SERVER_ERROR

        return {
            "message": "Stock level updated",
            "new_stock": item.quantity,
        }, status.HTTP_200_OK

    def _check_restock_status(self, item):
        """Check if item needs restocking"""
        if item.quantity < item.restock_level:
            app.logger.info(f"Restock alert triggered for item {item.id}")
            return {"message": "Restock alert triggered"}, status.HTTP_200_OK

        app.logger.info(f"No restock needed for item {item.id}")
        return {
            "message": "Stock level is above the restock threshold. No action needed."
        }, status.HTTP_200_OK


######################################################################
# Checks the ContentType of a request
######################################################################


def check_content_type(content_type):
    """Checks that the media type is correct"""
    if "Content-Type" not in request.headers:
        app.logger.error("No Content-Type specified.")
        raise BadRequest(f"Content-Type must be {content_type}")

    if request.headers["Content-Type"] != content_type:
        app.logger.error("Invalid Content-Type: %s", request.headers["Content-Type"])
        raise BadRequest(f"Content-Type must be {content_type}")


# @app.route('/inventory', methods=['GET'])
# def index_page():
#     """Renders the index page."""
#     return render_template('index.html')
