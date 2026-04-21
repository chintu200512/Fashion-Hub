from database.mongodb_connection import MongoDB
from datetime import datetime
import uuid
from bson import ObjectId

class Order:
    collection = MongoDB.get_collection('orders')
    
    @classmethod
    def create_order(cls, user_id, items, total_amount, shipping_address, payment_method):
        order = {
            "order_id": str(uuid.uuid4()),
            "user_id": str(user_id),  # Store as string
            "items": items,
            "total_amount": total_amount,
            "shipping_address": shipping_address,
            "payment_method": payment_method,
            "order_status": "pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = cls.collection.insert_one(order)
        return str(result.inserted_id)
    
    @classmethod
    def get_user_orders(cls, user_id):
        """Get all orders for a user"""
        try:
            user_id_str = str(user_id)
            orders_cursor = cls.collection.find({"user_id": user_id_str}).sort("created_at", -1)
            
            orders = []
            for order in orders_cursor:
                order['_id'] = str(order['_id'])
                orders.append(order)
            
            return orders
        except Exception as e:
            print(f"Error in get_user_orders: {e}")
            return []