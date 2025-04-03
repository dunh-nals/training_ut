import unittest
from unittest.mock import Mock, patch

from order_processing import (
    Order, OrderType, OrderStatus, OrderError, OrderPriority, OrderProcessingService,
    ExportOrderProcessor, APIOrderProcessor, SimpleOrderProcessor, UnknownOrderProcessor,
    PriorityCalculator, DatabaseService, APIClient, FileExporter, APIResponse,
    DatabaseException, APIException, FileExportException, ProcessingResult, Configuration, CSVFileExporter
)

class TestOrderProcessing(unittest.TestCase):
    def setUp(self):
        self.db_service = Mock(spec=DatabaseService)
        self.api_client = Mock(spec=APIClient)
        self.file_exporter = Mock(spec=FileExporter)
        self.service = OrderProcessingService(self.db_service, self.api_client, self.file_exporter)

    # Test processing when no orders are returned from the database
    def test_process_orders_no_orders(self):
        self.db_service.get_orders_by_user.return_value = []
        result = self.service.process_orders(user_id=1)
        self.assertFalse(result)
        self.db_service.get_orders_by_user.assert_called_once_with(1)
        self.db_service.update_order_status.assert_not_called()

    # Test successful processing of an export order with high priority
    def test_process_orders_export_order_success(self):
        order = Order(id=1, type=OrderType.EXPORT, amount=Configuration.HIGH_PRIORITY_THRESHOLD + 1, flag=True)
        self.db_service.get_orders_by_user.return_value = [order]
        self.db_service.update_order_status.return_value = True
        result = self.service.process_orders(user_id=1)
        self.assertTrue(result)
        self.file_exporter.export_order_to_file.assert_called_once_with(order, 1)
        self.assertEqual(order.status, OrderStatus.EXPORTED)
        self.assertEqual(order.priority, OrderPriority.HIGH)
        self.db_service.update_order_status.assert_called_once_with(1, OrderStatus.EXPORTED, OrderPriority.HIGH)

    # Test processing an export order when file export fails
    def test_process_orders_export_order_file_export_fails(self):
        order = Order(id=1, type=OrderType.EXPORT, amount=100, flag=True)
        self.db_service.get_orders_by_user.return_value = [order]
        self.file_exporter.export_order_to_file.side_effect = FileExportException("File export error")
        self.db_service.update_order_status.return_value = True
        result = self.service.process_orders(user_id=1)
        self.assertTrue(result)
        self.assertEqual(order.status, OrderError.EXPORT_FAILED)
        self.assertEqual(order.priority, OrderPriority.LOW)
        self.db_service.update_order_status.assert_called_once_with(1, OrderError.EXPORT_FAILED, OrderPriority.LOW)

    # Test successful processing of an API order with "processed" status
    def test_process_orders_api_order_success_processed(self):
        order = Order(id=2, type=OrderType.API, amount=Configuration.API_AMOUNT_THRESHOLD - 1, flag=False)
        self.db_service.get_orders_by_user.return_value = [order]
        self.api_client.call_api.return_value = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD)
        self.db_service.update_order_status.return_value = True
        result = self.service.process_orders(user_id=1)
        self.assertTrue(result)
        self.assertEqual(order.status, OrderStatus.PROCESSED)
        self.assertEqual(order.priority, OrderPriority.LOW)
        self.db_service.update_order_status.assert_called_once_with(2, OrderStatus.PROCESSED, OrderPriority.LOW)

    # Test processing an API order when API call fails
    def test_process_orders_api_order_api_failure(self):
        order = Order(id=2, type=OrderType.API, amount=50, flag=False)
        self.db_service.get_orders_by_user.return_value = [order]
        self.api_client.call_api.side_effect = APIException("API Failure")
        self.db_service.update_order_status.return_value = True
        result = self.service.process_orders(user_id=1)
        self.assertTrue(result)
        self.assertEqual(order.status, OrderError.API_FAILURE)
        self.db_service.update_order_status.assert_called_once_with(2, OrderError.API_FAILURE, OrderPriority.LOW)

    # Test successful processing of a simple order with "completed" status
    def test_process_orders_simple_order_completed(self):
        order = Order(id=3, type=OrderType.SIMPLE, amount=300, flag=True)
        self.db_service.get_orders_by_user.return_value = [order]
        self.db_service.update_order_status.return_value = True
        result = self.service.process_orders(user_id=1)
        self.assertTrue(result)
        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertEqual(order.priority, OrderPriority.HIGH)
        self.db_service.update_order_status.assert_called_once_with(3, OrderStatus.COMPLETED, OrderPriority.HIGH)

    # Test processing an order with an unknown type
    def test_process_orders_unknown_type(self):
        order = Order(id=4, type=OrderType.UNKNOWN, amount=50, flag=False)
        self.db_service.get_orders_by_user.return_value = [order]
        self.db_service.update_order_status.return_value = True
        result = self.service.process_orders(user_id=1)
        self.assertTrue(result)
        self.assertEqual(order.status, OrderError.UNKNOWN_TYPE)
        self.assertEqual(order.priority, OrderPriority.LOW)
        self.db_service.update_order_status.assert_called_once_with(4, OrderError.UNKNOWN_TYPE, OrderPriority.LOW)

    # Test processing when database update fails (returns False)
    def test_process_orders_db_update_fails(self):
        order = Order(id=5, type=OrderType.SIMPLE, amount=50, flag=False)
        self.db_service.get_orders_by_user.return_value = [order]
        self.db_service.update_order_status.return_value = False
        result = self.service.process_orders(user_id=1)
        self.assertFalse(result)
        self.assertEqual(order.status, OrderError.DB_ERROR)
        self.db_service.update_order_status.assert_called_once_with(5, OrderStatus.IN_PROGRESS, OrderPriority.LOW)

    # Test processing when database update throws an exception
    def test_process_orders_db_exception(self):
        order = Order(id=5, type=OrderType.SIMPLE, amount=50, flag=False)
        self.db_service.get_orders_by_user.return_value = [order]
        self.db_service.update_order_status.side_effect = DatabaseException("Database error")
        result = self.service.process_orders(user_id=1)
        self.assertFalse(result)
        self.assertEqual(order.status, OrderError.DB_ERROR)
        self.db_service.update_order_status.assert_called_once_with(5, OrderStatus.IN_PROGRESS, OrderPriority.LOW)

    # Test processing multiple orders with one export failure
    def test_process_orders_multiple_orders_with_one_failure(self):
        order1 = Order(id=1, type=OrderType.SIMPLE, amount=50, flag=True)
        order2 = Order(id=2, type=OrderType.EXPORT, amount=100, flag=True)
        self.db_service.get_orders_by_user.return_value = [order1, order2]
        self.db_service.update_order_status.return_value = True
        self.file_exporter.export_order_to_file.side_effect = FileExportException("Export failed")
        result = self.service.process_orders(user_id=1)
        self.assertTrue(result)
        self.assertEqual(order1.status, OrderStatus.COMPLETED)
        self.assertEqual(order2.status, OrderError.EXPORT_FAILED)
        self.db_service.update_order_status.assert_any_call(1, OrderStatus.COMPLETED, OrderPriority.LOW)
        self.db_service.update_order_status.assert_any_call(2, OrderError.EXPORT_FAILED, OrderPriority.LOW)

    # Test processing when a general exception occurs
    def test_process_orders_general_exception(self):
        self.db_service.get_orders_by_user.side_effect = Exception("General error")
        result = self.service.process_orders(user_id=1)
        self.assertFalse(result)

class TestExportOrderProcessor(unittest.TestCase):
    def setUp(self):
        self.file_exporter = Mock(spec=FileExporter)
        self.processor = ExportOrderProcessor(self.file_exporter, user_id=1)

    # Test successful processing of an export order
    def test_process_export_success(self):
        order = Order(id=1, type=OrderType.EXPORT, amount=100, flag=True)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.EXPORTED))
        self.assertEqual(order.status, OrderStatus.EXPORTED)
        self.file_exporter.export_order_to_file.assert_called_once_with(order, 1)

    # Test processing an export order when export fails
    def test_process_export_failed(self):
        order = Order(id=1, type=OrderType.EXPORT, amount=100, flag=True)
        self.file_exporter.export_order_to_file.side_effect = FileExportException("Export failed")
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(error=OrderError.EXPORT_FAILED))

class TestAPIOrderProcessor(unittest.TestCase):
    def setUp(self):
        self.api_client = Mock(spec=APIClient)
        self.processor = APIOrderProcessor(self.api_client)

    # Test successful processing of an API order with "processed" status
    def test_process_api_success_processed(self):
        order = Order(id=2, type=OrderType.API, amount=Configuration.API_AMOUNT_THRESHOLD - 1, flag=False)
        self.api_client.call_api.return_value = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.PROCESSED))

    # Test processing an API order with "pending" status due to low data
    def test_process_api_pending_due_to_low_data(self):
        order = Order(id=2, type=OrderType.API, amount=150, flag=False)
        self.api_client.call_api.return_value = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD - 1)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.PENDING))

    # Test processing an API order with "pending" status due to flag
    def test_process_api_pending_due_to_flag(self):
        order = Order(id=2, type=OrderType.API, amount=150, flag=True)
        self.api_client.call_api.return_value = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.PENDING))

    # Test processing an API order when API call fails
    def test_process_api_failure(self):
        order = Order(id=2, type=OrderType.API, amount=50, flag=False)
        self.api_client.call_api.side_effect = APIException("API Failure")
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(error=OrderError.API_FAILURE))

    # Test processing an API order with "api_error" due to failed response
    def test_process_api_error_response(self):
        order = Order(id=2, type=OrderType.API, amount=50, flag=False)
        self.api_client.call_api.return_value = APIResponse(status='failed', data=0)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(error=OrderError.API_ERROR))

    # Test processing an API order with "error" status
    def test_process_api_error_status(self):
        order = Order(id=2, type=OrderType.API, amount=Configuration.API_AMOUNT_THRESHOLD, flag=False)
        self.api_client.call_api.return_value = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.ERROR))

    # Test determining "processed" status for an API order
    def test_determine_status_processed(self):
        order = Order(id=2, type=OrderType.API, amount=Configuration.API_AMOUNT_THRESHOLD - 1, flag=False)
        api_response = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD)
        result = self.processor.determine_status(api_response, order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.PROCESSED))

    # Test determining "pending" status due to low data for an API order
    def test_determine_status_pending_due_to_low_data(self):
        order = Order(id=2, type=OrderType.API, amount=150, flag=False)
        api_response = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD - 1)
        result = self.processor.determine_status(api_response, order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.PENDING))

    # Test determining "pending" status due to flag for an API order
    def test_determine_status_pending_due_to_flag(self):
        order = Order(id=2, type=OrderType.API, amount=150, flag=True)
        api_response = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD)
        result = self.processor.determine_status(api_response, order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.PENDING))

    # Test determining "api_error" status for an API order
    def test_determine_status_api_error(self):
        order = Order(id=2, type=OrderType.API, amount=50, flag=False)
        api_response = APIResponse(status='failed', data=0)
        result = self.processor.determine_status(api_response, order)
        self.assertEqual(result, ProcessingResult(error=OrderError.API_ERROR))

    # Test determining "error" status for an API order
    def test_determine_status_error(self):
        order = Order(id=2, type=OrderType.API, amount=Configuration.API_AMOUNT_THRESHOLD, flag=False)
        api_response = APIResponse(status='success', data=Configuration.API_DATA_THRESHOLD)
        result = self.processor.determine_status(api_response, order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.ERROR))

class TestSimpleOrderProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = SimpleOrderProcessor()

    # Test processing a simple order with "completed" status
    def test_process_simple_completed(self):
        order = Order(id=3, type=OrderType.SIMPLE, amount=100, flag=True)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.COMPLETED))

    # Test processing a simple order with "in_progress" status
    def test_process_simple_in_progress(self):
        order = Order(id=3, type=OrderType.SIMPLE, amount=100, flag=False)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(status=OrderStatus.IN_PROGRESS))

class TestUnknownOrderProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = UnknownOrderProcessor()

    # Test processing an order with an unknown type
    def test_process_unknown_type(self):
        order = Order(id=4, type=OrderType.UNKNOWN, amount=50, flag=False)
        result = self.processor.process(order)
        self.assertEqual(result, ProcessingResult(error=OrderError.UNKNOWN_TYPE))

class TestPriorityCalculator(unittest.TestCase):
    def setUp(self):
        self.calculator = PriorityCalculator()

    # Test determining "high" priority when amount exceeds threshold
    def test_determine_priority_high(self):
        amount = Configuration.HIGH_PRIORITY_THRESHOLD + 1
        result = self.calculator.determine_priority(amount)
        self.assertEqual(result, OrderPriority.HIGH)

    # Test determining "low" priority when amount equals threshold
    def test_determine_priority_low_at_threshold(self):
        amount = Configuration.HIGH_PRIORITY_THRESHOLD
        result = self.calculator.determine_priority(amount)
        self.assertEqual(result, OrderPriority.LOW)

    # Test determining "low" priority when amount is below threshold
    def test_determine_priority_low_below_threshold(self):
        amount = Configuration.HIGH_PRIORITY_THRESHOLD - 0.01
        result = self.calculator.determine_priority(amount)
        self.assertEqual(result, OrderPriority.LOW)

class TestCSVFileExporter(unittest.TestCase):
    def setUp(self):
        self.exporter = CSVFileExporter()

    # Test successful CSV file export with a high-value order
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    @patch('csv.writer')
    def test_export_order_to_file_success_high_value(self, mock_csv_writer, mock_open):
        order = Order(id=1, type=OrderType.EXPORT, amount=Configuration.HIGH_VALUE_ORDER_THRESHOLD + 1, flag=True)
        order.status = OrderStatus.EXPORTED
        mock_writer = Mock()
        mock_csv_writer.return_value = mock_writer
        self.exporter.export_order_to_file(order, user_id=1)
        mock_writer.writerow.assert_any_call(['ID', 'Type', 'Amount', 'Flag', 'Status', 'Priority'])
        mock_writer.writerow.assert_any_call([
            order.id,
            order.type.value,
            order.amount,
            str(order.flag).lower(),
            order.status.value,
            order.priority.value
        ])
        mock_writer.writerow.assert_any_call(['', '', '', '', 'Note', 'High value order'])

    # Test CSV file export failure due to IO error
    @patch('builtins.open', side_effect=IOError("IO Error"))
    def test_export_order_to_file_io_error(self, mock_open):
        order = Order(id=1, type=OrderType.EXPORT, amount=100, flag=True)
        with self.assertRaises(FileExportException) as context:
            self.exporter.export_order_to_file(order, user_id=1)
        self.assertIn("Can not export csv", str(context.exception))