<!DOCTYPE html>
<html lang="en-US">
<head>
  <title>Quantité de pluie à Vayrac</title>
  <meta name="viewport" content="width=device-width">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel='stylesheet' href='/static/style.css'>
</head>
<body>
  % if msg is not None:
  <p>{{ msg }}</p>
  % end
  <form class="form-inline" action="" method="POST">
  <label for="pluie">Quantité de pluie à Vayrac:</label>
  <input type="number" id="pluie" placeholder="quantité de pluie" name="pluie" required>

  <button type="submit">Envoyer</button>
</form>
</body>
</html>
