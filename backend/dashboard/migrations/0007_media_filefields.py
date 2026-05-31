from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0006_busroute_circular_inventoryitem_kanbanboard_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='photo',
            name='image',
            field=models.FileField(upload_to='gallery/'),
        ),
        migrations.AlterField(
            model_name='visitorlog',
            name='photo',
            field=models.FileField(blank=True, null=True, upload_to='visitors/'),
        ),
    ]
