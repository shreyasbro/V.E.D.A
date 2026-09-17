import unittest
from veda.notifications import notification_manager, Notification

class TestNotifications(unittest.TestCase):
    def setUp(self):
        notification_manager.clear_all()

    def test_add_and_get_notification(self):
        n = notification_manager.add_notification(
            category="UPDATE",
            title="Update Ready",
            message="Version 1.1.0 available",
            action_type="UPDATE_NOW"
        )
        self.assertIsNotNone(n.id)
        self.assertEqual(notification_manager.get_unread_count(), 1)
        notifs = notification_manager.get_notifications()
        self.assertEqual(len(notifs), 1)
        self.assertEqual(notifs[0].title, "Update Ready")

    def test_deduplication(self):
        n1 = notification_manager.add_notification(
            category="UPDATE",
            title="V.E.D.A. Update Available",
            message="Version 1.1.0 is ready."
        )
        n2 = notification_manager.add_notification(
            category="UPDATE",
            title="V.E.D.A. Update Available",
            message="Version 1.1.0 is ready now."
        )
        self.assertEqual(n1.id, n2.id)
        self.assertEqual(notification_manager.get_unread_count(), 1)

    def test_mark_as_read_and_dismiss(self):
        n = notification_manager.add_notification("SYSTEM", "Test", "Msg")
        self.assertEqual(notification_manager.get_unread_count(), 1)
        notification_manager.mark_as_read(n.id)
        self.assertEqual(notification_manager.get_unread_count(), 0)
        notification_manager.dismiss(n.id)
        self.assertEqual(len(notification_manager.get_notifications()), 0)

if __name__ == '__main__':
    unittest.main()
