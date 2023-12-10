import json
import sys
import os

import datetime
import bottle
import prometheus_client
import prometheus_client.parser

METRICS_FILE = "out/metrics.txt"
LABELS_COUNT = 3

existing_metrics = {}

last_update = {}

@bottle.route('/static/<filepath:re:.*\.css>')
def css(filepath):
    return bottle.static_file(filepath, root="static/css")


def update_metric(metric_key, update_value, increase=True):
    metric = existing_metrics[metric_key]
    current_value = metric._samples()[0].value

    new_value = float(update_value)
    if increase:
        new_value += current_value

    metric.set(new_value)
    last_update[metric_key] = f"le {datetime.datetime.now().strftime('%Y-%m-%d à %H:%M')}", update_value

    return f"{metric._documentation} [{metric_key}] +{update_value} --> {new_value}", True


def new_metric(forms):
    name = forms["__new__.name"]
    descr = forms["__new__.description"]
    if descr == "exit":
        sys.stderr.close()
        return "Closing", False

    if descr == "delete":
        try:
            metric = existing_metrics.pop(name)
        except KeyError:
            return f"Métrique {name} n'existe pas :/"
        # prometheus_client.registry.REGISTRY.unregister(metric)

        return f"Métrique {name} supprimée", True

    labels = {}
    for label_id in range(LABELS_COUNT):
        label_name = forms.get(f"__new__.label{label_id}")
        if not label_name: continue
        label_value = forms.get(f"__new__.labelvalue{label_id}", "no value")
        labels[label_name] = label_value

    metric = prometheus_client.Gauge(name, descr, labels.keys())
    if labels:
        metric = metric.labels(*labels.values())
    metric.set(0)

    insert_metric(metric)

    return f"Métrique {name}{labels} crée :)", True


def insert_metric(metric):
    label_id = "-".join([f"{k}_{v}" for k, v in zip(metric._labelnames, metric._labelvalues)])

    existing_metrics[f"{metric._name}--{label_id}"] = metric


@bottle.route('/', method=["POST", "GET"])
def index():
    if bottle.request.forms:
        metric_key = bottle.request.forms["what"]
        if metric_key == "__new__":
            msg, save = new_metric(bottle.request.forms)
        else:
            new_value = bottle.request.forms[metric_key]
            do_increase = bottle.request.forms.get("__increase__", "true") == "true"
            msg, save = update_metric(metric_key, new_value, increase=do_increase)

        if save:
            prometheus_client.write_to_textfile(METRICS_FILE, prometheus_client.registry.REGISTRY)

    else:
        msg = None

    return bottle.template("index", metrics=existing_metrics.items(), msg=msg, LABELS_COUNT=LABELS_COUNT, last_update=last_update)

def load_metrics():
    with open(METRICS_FILE) as f:
        metrics = f.read()

    for family in prometheus_client.parser.text_string_to_metric_families(metrics):
        if family.name.startswith("process_"): continue
        if family.name.startswith("python_"): continue

        if family.type == "counter":
            metric_class = prometheus_client.Counter
        elif family.type == "gauge":
            metric_class = prometheus_client.Gauge
        metric_labels = set()

        for sample in family.samples:
            metric_labels |= sample.labels.keys()

        metric = metric_class(family.name, family.documentation, list(metric_labels))

        for sample in family.samples:
            full_metric = metric.labels(*sample.labels.values()) if sample.labels else metric
            full_metric.set(sample.value)

            insert_metric(full_metric)


@bottle.route('/metrics')
def metrics():
    return bottle.static_file(METRICS_FILE, root=".")


if __name__ == "__main__":
    load_metrics()
    for m in existing_metrics.values():
        labels = dict(zip(m._labelnames, m._labelvalues))
        print(m, m._documentation, labels)

    bottle.run(host='localhost', port=int(os.environ.get("BOTTLE_PORT", 8080)), reloader=True)
