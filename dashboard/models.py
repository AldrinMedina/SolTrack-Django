from django.db import models
from accounts.models import CustomUser
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings



class Contract(models.Model):
    contract_id = models.AutoField(primary_key=True)
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL,
                              related_name="contracts_bought",
                              on_delete=models.CASCADE)

    seller = models.ForeignKey(settings.AUTH_USER_MODEL,
                               related_name="contracts_sold",
                               on_delete=models.CASCADE)

    buyer_address = models.CharField(max_length=100)
    seller_address = models.CharField(max_length=100)

    price = models.DecimalField(max_digits=12, decimal_places=4)
    final_price  = models.DecimalField(max_digits=12, decimal_places=4)
    min_temp = models.IntegerField()
    max_temp = models.IntegerField()

    temperature_time = models.IntegerField(
        default=3,
        help_text="Temperature breach duration (minutes) before refund"
    )

    product_name = models.CharField(max_length=100) 
    quantity = models.IntegerField()

    IoT_Assigned = models.ForeignKey(
        'IoTDevice',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_contract',
        db_column='IoT_Assigned'
    )

    contract_address = models.CharField(max_length=200, null=True, blank=True)
    contract_abi = models.TextField(null=True, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    rejection_refund_reason = models.TextField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ('Pending', 'Pending'),
            ('Active', 'Active'),
            ('Ongoing', 'Ongoing'),
            ('Completed', 'Completed'),
            ('Refunded', 'Refunded'),
        ],
        default='Pending'
    )

    class Meta:
        db_table = 'contracts'
        managed = False

    def __str__(self):
        return f"Contract #{self.pk} | {self.status}"

class ContractAddresses(models.Model):
    id = models.AutoField(primary_key=True)
    contract = models.OneToOneField('Contract', on_delete=models.CASCADE, related_name='address_record')

    # TX hashes
    contract_address = models.CharField(max_length=42)
    contract_tx = models.CharField(max_length=255, null=True, blank=True)
    escrow_init_tx = models.CharField(max_length=255, null=True, blank=True)
    init_payment_add = models.CharField(max_length=255, null=True, blank=True)
    final_payment_add = models.CharField(max_length=255, null=True, blank=True)
    escrow_final_tx = models.CharField(max_length=255, null=True, blank=True)

    # GAS INFO (json fields)
    contract_gas = models.JSONField(null=True, blank=True)
    escrow_init_gas = models.JSONField(null=True, blank=True)
    init_payment_gas = models.JSONField(null=True, blank=True)
    final_payment_gas = models.JSONField(null=True, blank=True)
    escrow_final_gas = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'contract_addresses'
        managed = False
    
class Product(models.Model):
    product_id = models.AutoField(primary_key=True)
    seller = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="products")
    product_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price_eth = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    quantity_available = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    min_temp = models.FloatField(default=2)
    max_temp = models.FloatField(default=8)
    temp_time_range = models.IntegerField(default=60) 
    class Meta:
        db_table = 'products'
        managed = False  # Prevent Django from managing this table
    def __str__(self):
        return f"{self.product_name} ({self.seller.full_name})"




class IoTDevice(models.Model):
    device_id = models.AutoField(primary_key=True)
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='devices',
        null=True,
        blank=True
    )
    device_name = models.CharField(max_length=255)
    adafruit_feed = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, default='Available')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iot_devices'
        managed = False

    def __str__(self):
        return f"{self.device_name} ({self.status})"
class Alert(models.Model):
    ALERT_SEVERITY = (
        ('Critical', 'Critical'),
        ('Warning', 'Warning'),
        ('Info', 'Info'),
    )
    alert_id = models.AutoField(primary_key=True)
    contract = models.ForeignKey(Contract, null=True, blank=True, on_delete=models.SET_NULL)
    device = models.ForeignKey(IoTDevice, null=True, blank=True, on_delete=models.SET_NULL)
    alert_type = models.CharField(max_length=255)
    alert_message = models.TextField()
    severity = models.CharField(max_length=20, choices=ALERT_SEVERITY, default='Warning')
    status = models.CharField(max_length=50, default='Active')
    is_read = models.BooleanField(default=False)
    category = models.CharField(max_length=50, default='System')
    metadata = models.JSONField(default=dict, blank=True)  # Django 3.1+
    triggered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'alerts'
        managed = False        
class ShipmentLog(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE)
    device = models.ForeignKey(IoTDevice, on_delete=models.CASCADE, null=True, blank=True)


    log_time = models.DateTimeField(default=timezone.now)     # When the event happened
    message = models.TextField()          # The summary text
    log_type = models.CharField(max_length=50, default='System')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        managed = False
        db_table = "ShipmentLog"  # makes table name explicit
        ordering = ["log_time"]
class IoTData(models.Model):
    data_id = models.AutoField(primary_key=True)
    device = models.ForeignKey(IoTDevice, on_delete=models.CASCADE,
                               db_column='device_id', related_name='iot_data')
    temperature = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(null=True, blank=True)
    contract = models.ForeignKey(
        'Contract', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        db_column='contract_id' # Ensure this matches your DB column name
    )
    class Meta:
        db_table = 'iot_data'
        managed = False


class IoTDataHistory(models.Model):
    history_id = models.AutoField(primary_key=True)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE,
                                 related_name='iot_history', null=True, blank=True)
    avg_temp = models.FloatField()
    min_temp = models.FloatField()
    max_temp = models.FloatField()
    result = models.CharField(max_length=50, default='Normal')
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iot_data_history'
        managed = False

