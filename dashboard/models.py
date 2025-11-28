from django.db import models
from accounts.models import CustomUser

class Contract(models.Model):
    # Matches DB: SERIAL PRIMARY KEY -> IntegerField
    contract_id = models.IntegerField(primary_key=True) 
    buyer_address = models.CharField(max_length=42)
    seller_address = models.CharField(max_length=42)
    IoT_Assigned = models.ForeignKey(
        'IoTDevice', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='shipments',
        db_column='IoT_Assigned'
    )
    # Matches DB: VARCHAR(100)
    product_name = models.CharField(max_length=100) 
    # Matches DB: INT
    quantity = models.IntegerField() 
    # Matches DB: NUMERIC(12,2)
    price = models.DecimalField(max_digits=12, decimal_places=2) 
    
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)  
    
    # Matches DB: VARCHAR(255). 42 is sufficient, but 255 is fine.
    contract_address = models.CharField(max_length=42, default='NOT_DEPLOYED') 
    
    # NEW FIELD: Uses Django's JSONField, which maps to PostgreSQL's JSONB type
    contract_abi = models.JSONField(default=dict)

    min_temp = models.FloatField(default=2) # Or another suitable default
    max_temp = models.FloatField(default=8) 
    start_coord = models.CharField(max_length=50, null=True, blank=True) # Seller's location upon activation
    end_coord = models.CharField(max_length=50, null=True, blank=True)   # Buyer's location upon creation
    temperature_time = models.IntegerField(default=180)
    location_time = models.IntegerField(default=180)
    radius = models.FloatField(default=30)
    # Matches DB: VARCHAR(50). Default should match your DB if possible, but 'active' works for filtering.
    status = models.CharField(max_length=50,  choices=[
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('Pending', 'Pending'),
        ('Ongoing', 'Ongoing'),
        ('Refunded', 'Refunded'),
    ], default='Pending') 

    buyer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='buyer_contracts', null=True, blank=True)
    seller = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='seller_contracts', null=True, blank=True)

    class Meta:
        # Crucial: Link to your existing Supabase table name
        db_table = 'contracts' 
        managed = False

    def __str__(self):
        return f"{self.product_name} ({self.status})"
class ContractAddresses(models.Model):
    id = models.AutoField(primary_key=True)
    contract = models.OneToOneField('Contract', on_delete=models.CASCADE, related_name='address_record')
    contract_address = models.CharField(max_length=42)
    init_payment_add = models.CharField(max_length=255, null=True, blank=True)   # store init tx hash(es)
    final_payment_add = models.CharField(max_length=255, null=True, blank=True)  # store final payout tx hash

    class Meta:
        db_table = 'contract_addresses'
class IoTDevice(models.Model):
    device_id = models.AutoField(primary_key=True)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='devices', null=True, blank=True)
    device_name = models.CharField(max_length=255)
    adafruit_feed = models.CharField(max_length=255)
    status = models.CharField(max_length=50, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iot_devices'
        managed = False


class IoTDataHistory(models.Model):
    history_id = models.AutoField(primary_key=True)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='iot_history', null=True, blank=True)
    avg_temp = models.FloatField()
    min_temp = models.FloatField()
    max_temp = models.FloatField()
    result = models.CharField(max_length=50, default='Normal')
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'iot_data_history'
        managed = False


class Alert(models.Model):
    alert_id = models.AutoField(primary_key=True)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, db_column='contract_id')
    alert_type = models.CharField(max_length=50)
    alert_message = models.TextField()
    severity = models.CharField(max_length=20)
    status = models.CharField(max_length=20)
    triggered_at = models.DateTimeField()

    class Meta:
        db_table = 'alerts'
        managed = False

class IoTData(models.Model):
    data_id = models.AutoField(primary_key=True)
    device = models.ForeignKey(
        'IoTDevice', 
        on_delete=models.CASCADE, 
        db_column='device_id',
        related_name='iot_data'
    )
    temperature = models.FloatField(null=True, blank=True)
    battery_voltage = models.FloatField(null=True, blank=True)
    gps_lat = models.FloatField(null=True, blank=True)
    gps_long = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'iot_data'
        managed = False  # ✅ prevents Django from altering your real PostgreSQL table

    def __str__(self):
        return f"IoT Data #{self.data_id} - Device {self.device.device_id}"

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
