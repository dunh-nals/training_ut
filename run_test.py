from typing import List
from order_processing import (Order, OrderType, OrderStatus, OrderPriority,
                            DatabaseService, APIClient, APIResponse,
                            OrderProcessingService, CSVFileExporter)

# Mock DatabaseService
class MockDatabaseService(DatabaseService):
    def __init__(self):
        self.orders = {
            1: [
                Order(1, OrderType.EXPORT, 100.0, False),
                Order(2, OrderType.EXPORT, 180.0, False),
                Order(3, OrderType.API, 80.0, True),
                Order(4, OrderType.API, 120.0, False),
                Order(5, OrderType.SIMPLE, 250.0, True),
                Order(6, OrderType.SIMPLE, 150.0, False),
                Order(7, OrderType.UNKNOWN, 50.0, False),
            ]
        }

    def get_orders_by_user(self, user_id: int) -> List[Order]:
        return self.orders.get(user_id, [])

    def update_order_status(self, order_id: int, status: OrderStatus, priority: OrderPriority) -> bool:
        for order in self.orders[1]:
            if order.id == order_id:
                order.status = status
                order.priority = priority
                return True
        return False

# Mock APIClient
class MockAPIClient(APIClient):
    def call_api(self, order_id: int) -> APIResponse:
        if order_id == 3:
            return APIResponse("failed", 0)
        if order_id == 4:
            return APIResponse("success", 60)
        return APIResponse("success", 0)


def run_test():
    db_service = MockDatabaseService()
    api_client = MockAPIClient()
    file_exporter = CSVFileExporter()
    service = OrderProcessingService(db_service, api_client, file_exporter)

    user_id = 1
    result = service.process_orders(user_id)

    print(f"Processing result: {'Success' if result else 'Failed'}\n")
    print("Final Order Statuses:")
    for order in db_service.get_orders_by_user(user_id):
        print(f"Order ID: {order.id}, Type: {order.type.value}, "
              f"Status: {order.status.value}, Priority: {order.priority.value}")

if __name__ == "__main__":
    run_test()