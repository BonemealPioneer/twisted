/* cReactor.c - Implementation of the IReactorCore. */

/* includes */
#include "cReactor.h"
#include <stdio.h>
#include <signal.h>
#include <unistd.h>

/* Named constants. */
enum
{
    /* The initial size of the pollfd array. */
    CREACTOR_STARTING_POLLFD_SIZE       = 8,
};


/* Forward declare the cReactor type object. */
staticforward PyTypeObject cReactorType;

/* Small struct so we can pass more data through the user_data parameter to
 * cReactorUtil_ForEachMethod.
 */
typedef struct _SysEventInfo SysEventInfo;

struct _SysEventInfo
{
    cReactor *          reactor;
    cReactorEventType   event;
    int                 got_defers;
};


/* The currently running reactor, needed by the signal handlers. */
static cReactor * running_reactor = NULL;

PyObject *
cReactor_not_implemented(PyObject *self,
                         PyObject *args,
                         const char *text)
{
    UNUSED(self);
    UNUSED(args);

    PyErr_SetString(PyExc_NotImplementedError, text);
    return NULL;
}

static PyObject *
cReactor_resolve(PyObject *self, PyObject *args, PyObject *kw)
{
    const char *name;
    int type        = 1;
    int timeout     = 10;
    static char *kwlist[] = { "name", "type", "timeout", NULL };

    if (!PyArg_ParseTupleAndKeywords(args, kw, "s|ii:resolve", kwlist,
                                     &name, &type, &timeout))
    {
        return NULL;
    }
                                     
    return cReactor_not_implemented(self, args, "cReactor_resolve");
}


static void
run_system_event_triggers(PyObject *callable, PyObject *args, PyObject *kw, void *user_data)
{
    PyObject *result;

    UNUSED(user_data);

    /* Call the callable. */
    /*
    printf("calling ");
    PyObject_Print(callable, stdout, 1);
    printf("\n");
    */
    result = PyEval_CallObjectWithKeywords(callable, args, kw);
    if (!result)
    {
        PyErr_Print();
        return;
    }

    /* Ignore the return value. */
    Py_DECREF(result);
}


static void
finish_system_event(cReactor *reactor, cReactorEventType type)
{
    /* Run the "during" triggers. */
    cReactorUtil_ForEachMethod(reactor->event_triggers[type][CREACTOR_EVENT_PHASE_DURING],
                               run_system_event_triggers, NULL);

    /* Run the "after" triggers. */
    cReactorUtil_ForEachMethod(reactor->event_triggers[type][CREACTOR_EVENT_PHASE_AFTER],
                               run_system_event_triggers, NULL);

    /* If we are in the STOPPING state, move to DONE. */
    if (reactor->state == CREACTOR_STATE_STOPPING)
    {
        reactor->state = CREACTOR_STATE_DONE;
    }
}


static PyObject *
system_event_defer_callback(PyObject *self, PyObject *args)
{
    PyObject *defer_id;
    int i;
    int len;
    PyObject *empty_list;
    cReactor *reactor;
    int event_type;
    cReactorEventType event;
    
    reactor = (cReactor *)self;

    /* Check args. */
    if (!PyArg_ParseTuple(args, "Oi:system_event_defer_callback", &defer_id, &event_type))
    {
        return NULL;
    }

    /* Check arg 1. */
    if (!PyLong_Check(defer_id))
    {
        PyErr_Format(PyExc_ValueError, "system_event_defer_callback arg 1 expected long, found %s",
                     defer_id->ob_type->tp_name);
        return NULL;
    }

    /* Check arg 2. */
    switch (event_type)
    {
        case CREACTOR_EVENT_TYPE_STARTUP:
        case CREACTOR_EVENT_TYPE_SHUTDOWN:
        case CREACTOR_EVENT_TYPE_PERSIST:
            event = (cReactorEventType)event_type;
            break;

        default:
            PyErr_Format(PyExc_ValueError, "system_event_defer_callback arg 2 invalid event type: %d",
                         event_type);
            return NULL;
    }

    /* Remove the given defer id from the list. */
    len = PyList_Size(reactor->defer_list);
    for (i = 0; i < len; ++i)
    {
        /* We can do a direct compare because were looking for a specific
         * object.
         */
        if (PyList_GetItem(reactor->defer_list, i) == defer_id)
        {
            /* Found -- remove by replacing this piece with a slice. */
            empty_list = PyList_New(0);
            PyList_SetSlice(reactor->defer_list, i, i + 1, empty_list);
            Py_DECREF(empty_list);
            break;
        }
    }

    /* If the list is empty, we can finish the event processing. */
    if (PyList_Size(reactor->defer_list) == 0)
    {
        finish_system_event(reactor, event);
    }

    Py_INCREF(Py_None);
    return Py_None;
}


static void
run_before_system_event_triggers(PyObject *callable, PyObject *args, PyObject *kw, void *user_data)
{
    PyObject *defer;
    PyObject *deferred_class;
    PyObject *result;
    int is_defer;
    PyMethodDef callback_def;
    PyObject *callback;
    PyObject *defer_id;
    cReactor *reactor;
    SysEventInfo *event_info;

    event_info  = (SysEventInfo *)user_data;
    reactor     = event_info->reactor;

    /* Get the deferred class object. */
    deferred_class = cReactorUtil_FromImport("twisted.internet.defer", "Deferred");
    if (!deferred_class)
    {
        PyErr_Print();
        return;
    }

    /* Call the callable. */
    /*
    printf("calling ");
    PyObject_Print(callable, stdout, 1);
    printf("\n");
    */
    defer = PyEval_CallObjectWithKeywords(callable, args, kw);
    if (!defer)
    {
        Py_DECREF(deferred_class);
        PyErr_Print();
        return;
    }

    /* Check if the defer is a Deferred. */
    is_defer = PyObject_IsInstance(defer, deferred_class);
    Py_DECREF(deferred_class);
    
    if (is_defer)
    {
        /* Record the fact we got a Deferred as a return value. */
        event_info->got_defers = 1;

        /*
        printf("is_defer: ");
        PyObject_Print(defer, stdout, 1);
        printf("\n");
        */

        /* Instead of holding onto the deferred, hold onto its id() */
        defer_id = PyLong_FromVoidPtr(defer);

        /* Add the Deferred to the list. */
        if (PyList_Append(reactor->defer_list, defer_id) < 0)
        {
            Py_DECREF(defer_id);
            Py_DECREF(defer);
            PyErr_Print();
            return;
        }

        /* Create the PyCFunction to use for the callback. */
        callback_def.ml_name    = "system_event_defer_callback";
        callback_def.ml_meth    = system_event_defer_callback;
        callback_def.ml_flags   = METH_VARARGS;
        callback_def.ml_doc     = "system_event_defer_callback";
        callback                = PyCFunction_New(&callback_def, (PyObject *)reactor);

        /* Add a call/errback to the deferred. */
        result = PyObject_CallMethod(defer, "addBoth", "(OOi)",
                                     callback, defer_id, event_info->event);
        Py_DECREF(callback);
        Py_DECREF(defer_id);
        Py_XDECREF(result);

        if (!result)
        {
            PyErr_Print();
        }
    }
    else
    {
        Py_DECREF(defer);
    }
}


void
fireSystemEvent_internal(cReactor *reactor, cReactorEventType event)
{
    SysEventInfo event_info;

    /* Iterate over the "before" methods. */
    event_info.reactor      = reactor;
    event_info.event        = event;
    event_info.got_defers   = 0;
    cReactorUtil_ForEachMethod(reactor->event_triggers[event][CREACTOR_EVENT_PHASE_BEFORE],
                               run_before_system_event_triggers, &event_info);

    /* If we did not add any defers finish the system event. */
    if (! event_info.got_defers)
    {
        finish_system_event(reactor, event);
    }

}

static PyObject *
cReactor_fireSystemEvent(PyObject *self, PyObject *args)
{
    cReactor *reactor;
    const char *type_str;
    cReactorEventType event;

    reactor = (cReactor *)self;

    if (!PyArg_ParseTuple(args, "s:fireSystemEvent", &type_str))
    {
        return NULL;
    }
   
    /* Get the event event. */
    if (cReactorUtil_GetEventType(type_str, &event) < 0)
    {
        return NULL;
    }
    
    /* Fire the system event. */
    fireSystemEvent_internal(reactor, event);
    Py_INCREF(Py_None);
    return Py_None;
}

static void
stop_internal(cReactor *reactor)
{
    /* Change state and fire system event. */
    reactor->state = CREACTOR_STATE_STOPPING;
    fireSystemEvent_internal(reactor, CREACTOR_EVENT_TYPE_SHUTDOWN);
}


static PyObject *
cReactor_stop(PyObject *self, PyObject *args)
{
    /* No args. */
    if (!PyArg_ParseTuple(args, ":stop"))
    {
        return NULL;
    }
    
    stop_internal((cReactor *)self);
    Py_INCREF(Py_None);
    return Py_None;
}

static volatile int received_signal;

static void
cReactor_sighandler(int sig)
{
    /* Record the signal. */
    received_signal = sig;
}

static void
iterate_rebuild_pollfd_arrray(cReactor *reactor)
{
    unsigned int num_transports;
    struct pollfd *pfd;
    cReactorTransport *transport;
    cReactorTransport *shadow;
    cReactorTransport *target;

    /* Make sure we have enough space to hold everything. */
    if (reactor->pollfd_size < reactor->num_transports)
    {
        free(reactor->pollfd_array);
        reactor->pollfd_size    = reactor->num_transports * 2;
        reactor->pollfd_array   = (struct pollfd *)malloc(sizeof(struct pollfd *) * reactor->pollfd_size);
    }

    /* Fill in the pollfd event struct using the transport info. */
    num_transports  = 0;
    pfd             = reactor->pollfd_array;
    transport       = reactor->transports;
    shadow          = NULL;
    while (transport)
    {
        /* Check for transports that are closed. */
        if (transport->state == CREACTOR_TRANSPORT_STATE_CLOSED)
        {
            target      = transport;
            transport   = transport->next;

            /* Remove the target node from the linked list. */
            if (shadow)
            {
                shadow->next = transport;
            }
            else
            {
                reactor->transports = transport;
            }

            /* Call the close function. */
            cReactorTransport_Close(target);
            Py_DECREF((PyObject *)target);
        }
        else
        {
            /* The transport is still valid, so fill in a pollfd struct. */
            pfd->fd     = transport->fd;
            pfd->events = 0;

            /* If they are active and have a do_read function add the POLLIN
             * event. */
            if (   (transport->state == CREACTOR_TRANSPORT_STATE_ACTIVE)
                && transport->do_read)
            {
                pfd->events |= POLLIN;
            }

            /* If they have a do_write function and there is data in the write
             * buffer or they have a producer, add in the POLLOUT event. */
            if (   transport->do_write 
                && (   (cReactorBuffer_DataAvailable(transport->out_buf) > 0)
                    || transport->producer))
            {
                pfd->events |= POLLOUT;
            }

            /* Update the transport's pointer to the events mask */
            transport->event_mask = &pfd->events;

            ++pfd;
            ++num_transports;
            transport = transport->next;
        }
    }

    /* Update the number of active transports. */
    reactor->num_transports = num_transports;

    /* No longer stale. */
    reactor->pollfd_stale = 0;
}


static void
iterate_process_pollfd_array(cReactor *reactor)
{
    struct pollfd *pfd;
    cReactorTransport *transport;

    /* Iterate over the results. */
    for (pfd = reactor->pollfd_array, transport = reactor->transports;
         transport;
         ++pfd, transport = transport->next)
    {
        /* Check for any flags. */
        if (! pfd->revents)
        {
            continue;
        }

        if (pfd->revents & POLLIN)
        {
            cReactorTransport_Read(transport);
        }

        if (pfd->revents & POLLOUT)
        {
            cReactorTransport_Write(transport);
        }

        if (pfd->revents & (~(POLLIN | POLLOUT)))
        {
            /* TODO: Handle errors. */
            /* printf("fd=%d revents=0x%x\n", transport->fd, pfd->revents); */
            transport->state        = CREACTOR_TRANSPORT_STATE_CLOSED;
            reactor->pollfd_stale   = 1;
        }
    }
}

static int
iterate_internal(cReactor *reactor, int delay)
{
    int method_delay;
    time_t now;
    int sleep_delay;

    /* Record the currently running reactor. */
    if (running_reactor)
    {
        PyErr_Format(PyExc_RuntimeError, "a cReactor is currently running!");
        return -1;
    }
    running_reactor = reactor;

    /* Special one-time init handling. */
    if (reactor->state == CREACTOR_STATE_INIT)
    {
        /* Fire the the startup system event. */
        fireSystemEvent_internal(reactor, CREACTOR_EVENT_TYPE_STARTUP);

        /* Clear the received signal. */
        received_signal = 0;

        /* Install signal handlers. */
        signal(SIGINT, cReactor_sighandler);
        signal(SIGTERM, cReactor_sighandler);

        /* Change our state to running. */
        reactor->state = CREACTOR_STATE_RUNNING;
    }

    /* Figure out the method delay. */
    method_delay = cReactorUtil_NextMethodDelay(reactor->timed_methods);
    if (method_delay < 0)
    {
        /* No methods to run.  Sleep for the specified delay time. */
        sleep_delay = delay;
    }
    else if (delay >= 0)
    {
        /* Sleep until the next method or (at max) the given delay. */
        sleep_delay = (method_delay < delay) ? method_delay : delay;
    }
    else
    {
        /* Sleep until the next method. */
        sleep_delay = method_delay;
    }

    /* Refresh the pollfd list (if needed). */
    if (reactor->pollfd_stale)
    {
        iterate_rebuild_pollfd_arrray(reactor);
    }

    /* Look for activity. */
    if (poll(reactor->pollfd_array,
             reactor->num_transports,
             (sleep_delay * 1000)) < 0)
    {
        /* Anything other an EINTR raises an exception. */
        if (errno != EINTR)
        {
            PyErr_SetFromErrno(PyExc_RuntimeError);
            return -1;
        }
    }
    else
    {
        iterate_process_pollfd_array(reactor);
    }

    /* Run all the methods that need to run. */ 
    time(&now);
    cReactorUtil_RunMethods(&reactor->timed_methods, now);

    /* Lame signal handling for now. */
    if (received_signal)
    {
        if (reactor->state == CREACTOR_STATE_RUNNING)
        {
            /* Stop. */
            stop_internal(reactor);
        }
    }

    running_reactor = NULL;
    return 0;
}


static PyObject *
cReactor_iterate(PyObject *self, PyObject *args, PyObject *kw)
{
    cReactor *reactor;
    int delay   = 0;
    static char *kwlist[] = { "delay", NULL };

    /* Args. */
    if (!PyArg_ParseTupleAndKeywords(args, kw, "|i:delay", kwlist, &delay))
    {
        return NULL;
    }

    reactor = (cReactor *)self;

    /* Run once. */
    if (iterate_internal(reactor, delay) < 0)
    {
        return NULL;
    }

    Py_INCREF(Py_None);
    return Py_None;
}


static PyObject *
cReactor_run(PyObject *self, PyObject *args)
{
    cReactor *reactor;

    reactor = (cReactor *)self;

    /* We shouldn't get any args. */
    if (!PyArg_ParseTuple(args, ":run"))
    {
        return NULL;
    }

    /* Keep running until we hit the DONE state. */
    while (reactor->state != CREACTOR_STATE_DONE)
    {
        if (iterate_internal(reactor, -1) < 0)
        {
            return NULL;
        }
    }

    Py_INCREF(Py_None);
    return Py_None;
}


static PyObject *
cReactor_crash(PyObject *self, PyObject *args)
{
    return cReactor_not_implemented(self, args, "cReactor_crash");
}

static PyObject *
cReactor_callFromThread(PyObject *self, PyObject *args)
{
    return cReactor_not_implemented(self, args, "cReactor_callFromThread");
}

static PyObject *
cReactor_addSystemEventTrigger(PyObject *self, PyObject *args, PyObject *kw)
{
    cReactor *reactor;
    int method_id;
    PyObject *req_args          = NULL;
    PyObject *callable_args     = NULL;
    PyObject *callable          = NULL;
    const char *phase_str       = NULL;
    const char *event_type_str  = NULL;
    cReactorEventType event_type;
    cReactorEventPhase event_phase; 

    reactor = (cReactor *)self;

    /* Slice off the arguments we want to parse ourselves. */
    req_args = PyTuple_GetSlice(args, 0, 3);

    /* Now use PyArg_ParseTuple on the required args. */
    if (!PyArg_ParseTuple(req_args, "ssO:callLater", &phase_str, &event_type_str, &callable))
    {
        Py_DECREF(req_args);
        return NULL;
    }
    Py_DECREF(req_args);

    /*
    printf("addSystemEventTrigger: \"%s\" \"%s\" ", phase_str, event_type_str);
    PyObject_Print(callable, stdout, 1);
    printf("\n");
    */

    /* Phase can only be one of: "before", "during", and "after" */
    if (cReactorUtil_GetEventPhase(phase_str, &event_phase) < 0)
    {
        return NULL;
    }

    /* EventType can only be on of: "startup", "shutdown", and "persist" */
    if (cReactorUtil_GetEventType(event_type_str, &event_type) < 0)
    {
        return NULL;
    }

    /* Verify the given object is callable. */
    if (!PyCallable_Check(callable))
    {
        PyErr_Format(PyExc_TypeError, "addSystemEventTrigger() arg 3 expected callable, found %s",
                     callable->ob_type->tp_name);
        return NULL;
    }

    /* Now get the arguments to pass to the callable. */
    callable_args = PyTuple_GetSlice(args, 3, PyTuple_Size(args));

    /* Add this method to the appropriate list. */
    method_id = cReactorUtil_AddMethod(&(reactor->event_triggers[event_type][event_phase]),
                                       callable, callable_args, kw);
    Py_DECREF(callable_args);
    
    return PyInt_FromLong(method_id);
}


static PyObject *
cReactor_removeSystemEventTrigger(PyObject *self, PyObject *args)
{
    return cReactor_not_implemented(self, args, "cReactor_removeSystemEventTrigger");
}


void
cReactor_AddTransport(cReactor *reactor, cReactorTransport *transport)
{
    /* Add the new transport into the list.  This steals a reference. */
    transport->next         = reactor->transports;
    reactor->transports     = transport;
    ++(reactor->num_transports);
    
    /* PollFD array is now stale */
    reactor->pollfd_stale = 1;
}


static int
cReactor_init(cReactor *reactor)
{
    PyObject *obj;
    static const char * interfaces[] = 
    {
        "IReactorCore",
        "IReactorTime",
        "IReactorTCP",
    };

    /* Create the __implements__ attribute. */
    obj = cReactorUtil_MakeImplements(interfaces, sizeof(interfaces) / sizeof(interfaces[0]));
    if (!obj)
    {
        return -1;
    }

    /* Add the tuple into the attr dict. */
    if (PyDict_SetItemString(reactor->attr_dict, "__implements__", obj) != 0)
    {
        Py_DECREF(obj);
        return -1;
    }

    /* Add an attribute named __class__.  We will use our type object. */
    obj = (PyObject *)reactor->ob_type;
    if (PyDict_SetItemString(reactor->attr_dict, "__class__", obj) != 0)
    {
        return -1;
    }

    /* Set our state. */
    reactor->state = CREACTOR_STATE_INIT;
    return 0;
}


PyObject *
cReactor_New(void)
{
    cReactor *reactor;

    /* Create a new object. */
    reactor = PyObject_New(cReactor, &cReactorType);

    /* The object's attribute dictionary. */
    reactor->attr_dict = PyDict_New();

    /* List of timed methods. */
    reactor->timed_methods = NULL;

    /* Event triggers and the deferred list. */
    memset(reactor->event_triggers, 0x00, sizeof(reactor->event_triggers));
    reactor->defer_list = PyList_New(0);

    /* List of transports */
    reactor->transports         = NULL;
    reactor->num_transports     = 0;

    /* Array of pollfd structs. */
    reactor->pollfd_array       = (struct pollfd *)malloc(  sizeof(struct pollfd *)
                                                          * CREACTOR_STARTING_POLLFD_SIZE);
    reactor->pollfd_size        = CREACTOR_STARTING_POLLFD_SIZE;
    reactor->pollfd_stale       = 0;

    /* Attempt to initialize it. */
    if (   (! reactor->attr_dict)
        || (! reactor->defer_list)
        || (cReactor_init(reactor) < 0))
    {
        Py_DECREF((PyObject *)reactor);
        return NULL;
    }

    return (PyObject *)reactor;
}


static void
cReactor_dealloc(PyObject *self)
{
    cReactor *reactor;
    int t, p;
    cReactorTransport *transport;
    cReactorTransport *target;

    reactor = (cReactor *)self;

    Py_DECREF(reactor->attr_dict);
    reactor->attr_dict = NULL;
    
    cReactorUtil_DestroyMethods(reactor->timed_methods);
    reactor->timed_methods = NULL;

    for (t = 0; t < CREACTOR_NUM_EVENT_TYPES; ++t)
    {
        for (p = 0; p < CREACTOR_NUM_EVENT_PHASES; ++p)
        {
            cReactorUtil_DestroyMethods(reactor->event_triggers[t][p]);
            reactor->event_triggers[t][p] = NULL;
        }
    }

    Py_XDECREF(reactor->defer_list);
    reactor->defer_list = NULL;

    transport = reactor->transports;
    while (transport)
    {
        target      = transport;
        transport   = transport->next;
        Py_DECREF(target);
    }
    reactor->transports = NULL;

    free(reactor->pollfd_array);
    reactor->pollfd_array = NULL;

    PyObject_Del(self);
}

/* Available methods on the cReactor. */
static PyMethodDef cReactor_methods[] = 
{
    /* IReactorCore */
    { "resolve",                    (PyCFunction)cReactor_resolve,
      (METH_VARARGS | METH_KEYWORDS), "resolve" },
    { "run",                        cReactor_run,
      METH_VARARGS, "run" },
    { "stop",                       cReactor_stop,
      METH_VARARGS, "stop" },
    { "crash",                      cReactor_crash,
      METH_VARARGS, "crash" },
    { "iterate",                    (PyCFunction)cReactor_iterate,
      (METH_VARARGS | METH_KEYWORDS), "iterate" },
    { "callFromThread",             cReactor_callFromThread,
      METH_VARARGS, "callFromThread" },
    { "fireSystemEvent",            cReactor_fireSystemEvent,
      METH_VARARGS, "fireSystemEvent" },
    { "addSystemEventTrigger",      (PyCFunction)cReactor_addSystemEventTrigger,
      (METH_VARARGS | METH_KEYWORDS), "addSystemEventTrigger" },
    { "removeSystemEventTrigger",   cReactor_removeSystemEventTrigger,
      METH_VARARGS, "removeSystemEventTrigger" },

    /* IReactorTime */
    { "callLater",          (PyCFunction)cReactorTime_callLater,
      (METH_VARARGS | METH_KEYWORDS), "callLater" },
    { "cancelCallLater",    cReactorTime_cancelCallLater,
      METH_KEYWORDS,  "cancelCallLater" },

    /* IReactorTCP */
    { "listenTCP",          (PyCFunction)cReactorTCP_listenTCP,
      (METH_VARARGS | METH_KEYWORDS), "listenTCP" },
    { "clientTCP",          cReactorTCP_clientTCP,
      METH_VARARGS, "clientTCP" },

    { NULL, NULL, METH_VARARGS, NULL },
};

static PyObject *
cReactor_getattr(PyObject *self, char *attr_name)
{
    cReactor *reactor;
    PyObject *obj;
  
    reactor = (cReactor *)self;

    /* First check for a method with the given name.
     */
    obj = Py_FindMethod(cReactor_methods, self, attr_name);
    if (obj)
    {
        return obj;
    }

    /* Now check the attribute dictionary. */
    obj = PyDict_GetItemString(reactor->attr_dict, attr_name);

    /* If we didn't find anything raise PyExc_AttributeError. */
    if (!obj)
    {
        PyErr_SetString(PyExc_AttributeError, attr_name);
        return NULL;
    }

    /* PyDict_GetItemString returns a borrowed reference so we need to incref
     * it before returning it.
     */
    Py_INCREF(obj);
    return obj;
}

static PyObject *
cReactor_repr(PyObject *self)
{
    char buf[100];

    snprintf(buf, sizeof(buf) - 1, "<cReactor instance %p>", self);
    buf[sizeof(buf) - 1] = 0x00;

    return PyString_FromString(buf);
}

/* The cReactor type. */
static PyTypeObject cReactorType = 
{
    PyObject_HEAD_INIT(&PyType_Type)
    0,
    "cReactor",         /* tp_name */
    sizeof(cReactor),   /* tp_basicsize */
    0,                  /* tp_itemsize */
    cReactor_dealloc,   /* tp_dealloc */
    NULL,               /* tp_print */
    cReactor_getattr,   /* tp_getattr */
    NULL,               /* tp_setattr */
    NULL,               /* tp_compare */
    cReactor_repr,      /* tp_repr */
    NULL,               /* tp_as_number */
    NULL,               /* tp_as_sequence */
    NULL,               /* tp_as_mapping */
    NULL,               /* tp_hash */
    NULL,               /* tp_call */
    NULL,               /* tp_str */
    NULL,               /* tp_getattro */
    NULL,               /* tp_setattro */
    NULL,               /* tp_as_buffer */
    0,                  /* tp_flags */
    NULL,               /* tp_doc */
    NULL,               /* tp_traverse */
    NULL,               /* tp_clear */
    NULL,               /* tp_richcompare */
    0,                  /* tp_weaklistoffset */
};

/* vim: set sts=4 sw=4: */
